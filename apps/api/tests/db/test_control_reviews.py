"""Human review of manual controls (manual-control-review spec), on real PostgreSQL with RLS."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_api.modules.scanning.api import RESCORE_TASK
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B, auth
from .test_framework_detail import detail_catalog as detail_catalog
from .test_framework_detail import url as detail_url
from .test_members import events, org_with, uid
from .test_overview import overview_catalog as overview_catalog


def today() -> date:
    return datetime.now(UTC).date()


@pytest.fixture
def manual(superuser: Engine, detail_catalog: dict[str, str]) -> Iterator[dict[str, str]]:
    """An active manual control mapped to R2 and a retired manual control."""
    key = detail_catalog["active"]
    manual, retired = f"manual_{uuid.uuid4().hex}", f"retired_{uuid.uuid4().hex}"
    with superuser.begin() as conn:
        for control, retired_at in ((manual, None), (retired, datetime.now(UTC))):
            conn.execute(
                text(
                    "INSERT INTO controls (key, title_es, title_en, description_es,"
                    " description_en, manual, retired_at) VALUES (:k, 'Revisión', 'Review',"
                    " 'Documento', 'Document', true, :r)"
                ),
                {"k": control, "r": retired_at},
            )
        conn.execute(
            text(
                "INSERT INTO mappings (framework_key, requirement_code, control_key, rationale,"
                " source) VALUES (:f, 'R2', :c, 'synthetic rationale', 'synthetic source')"
            ),
            {"f": key, "c": manual},
        )
    yield {**detail_catalog, "manual": manual, "retired": retired}
    with superuser.begin() as conn:  # reviews stay: append-only tenant rows, no catalog FK
        conn.execute(text("DELETE FROM mappings WHERE control_key = :c"), {"c": manual})
        conn.execute(
            text("DELETE FROM controls WHERE key IN (:a, :b)"), {"a": manual, "b": retired}
        )


def reviews_url(org: str, control: str) -> str:
    return f"/api/v1/orgs/{org}/controls/{control}/reviews"


def body(**overrides: object) -> dict[str, object]:
    base = {
        "status": "pass",
        "rationale": "Política de respuesta a incidentes aprobada por la dirección el 2026-10-01.",
        "valid_until": (today() + timedelta(days=365)).isoformat(),
    }
    return {**base, **overrides}


def cite(
    client: TestClient, org: str, sub: str, control: str, title: str = "Acta del comité"
) -> str:
    """Record an evidence statement on the control; a pass review cites one (#262)."""
    response = client.post(
        f"/api/v1/orgs/{org}/controls/{control}/evidence",
        json={"submission_id": str(uuid.uuid4()), "title": title, "statement": "Aprobada."},
        headers=auth(sub),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def passing(client: TestClient, org: str, sub: str, control: str, **overrides: object) -> dict:
    return body(evidence_ids=[cite(client, org, sub, control)], **overrides)


# --- recording -----------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["owner", "admin"])
def test_owner_and_admin_record_a_review(
    client: TestClient, superuser: Engine, manual: dict[str, str], role: str
) -> None:
    org, subs = org_with(client, superuser, admin="admin")
    response = client.post(
        reviews_url(org, manual["manual"]),
        json=passing(client, org, subs[role], manual["manual"]),
        headers=auth(subs[role]),
    )
    assert response.status_code == 201, response.text
    review = response.json()
    assert review["control_key"] == manual["manual"]
    assert review["status"] == "pass"
    assert review["reviewed_by"] == uid(client, subs[role])
    assert review["valid_until"] == body()["valid_until"]
    assert review["expired"] is False
    assert events(superuser, org, "control.reviewed") == 1


def test_audit_metadata_never_carries_the_rationale(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    client.post(
        reviews_url(org, manual["manual"]),
        json=passing(client, org, subs["owner"], manual["manual"]),
        headers=auth(subs["owner"]),
    )
    with superuser.connect() as conn:
        target, metadata = conn.execute(
            text(
                "SELECT target_id, metadata FROM audit_events"
                " WHERE organization_id = :o AND action = 'control.reviewed'"
            ),
            {"o": org},
        ).one()
    assert target == manual["manual"]
    assert metadata == {
        "status": "pass",
        "valid_until": body()["valid_until"],
        "evidence_count": 1,
    }


def test_a_member_cannot_record_and_a_stranger_sees_nothing(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser, member="member")
    _, others = org_with(client, superuser)
    path = reviews_url(org, manual["manual"])
    member = client.post(path, json=body(), headers=auth(subs["member"]))
    assert (member.status_code, member.json()["detail"]["code"]) == (403, "identity.forbidden")
    stranger = client.post(path, json=body(), headers=auth(others["owner"]))
    assert (stranger.status_code, stranger.json()["detail"]["code"]) == (
        404,
        "identity.not_found",
    )
    assert client.get(path, headers=auth(others["owner"])).status_code == 404
    assert events(superuser, org, "control.reviewed") == 0


@pytest.mark.parametrize(
    ("control", "status", "code"),
    [
        ("retired", 404, "compliance.control_not_found"),
        ("missing", 404, "compliance.control_not_found"),
        ("control", 409, "compliance.control_not_manual"),
    ],
)
def test_only_active_manual_controls_are_reviewed(
    client: TestClient,
    superuser: Engine,
    manual: dict[str, str],
    control: str,
    status: int,
    code: str,
) -> None:
    org, subs = org_with(client, superuser)
    key = manual.get(control, "no_such_control")
    response = client.post(reviews_url(org, key), json=body(), headers=auth(subs["owner"]))
    assert (response.status_code, response.json()["detail"]["code"]) == (status, code)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "not_applicable"},
        {"status": "manual"},
        {"rationale": "   "},
        {"rationale": "x" * 2001},
        {"rationale": "approved\x00"},
        {"rationale": "approved\x1b[31m"},
        {"valid_until": "today"},
        {"valid_until": "past"},
        {"valid_until": "too_far"},
    ],
)
def test_invalid_reviews_are_rejected(
    client: TestClient, superuser: Engine, manual: dict[str, str], overrides: dict[str, str]
) -> None:
    dates = {
        "today": today(),
        "past": today() - timedelta(days=1),
        "too_far": today() + timedelta(days=3 * 365 + 2),
    }
    if "valid_until" in overrides:
        overrides = {"valid_until": dates[overrides["valid_until"]].isoformat()}
    org, subs = org_with(client, superuser)
    response = client.post(
        reviews_url(org, manual["manual"]), json=body(**overrides), headers=auth(subs["owner"])
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "request.invalid"
    assert "approved" not in response.text


def test_rationale_keeps_line_breaks_and_is_trimmed(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    response = client.post(
        reviews_url(org, manual["manual"]),
        json=body(status="fail", rationale="  Acta 12:\n\tpunto 3 aprobado.  "),
        headers=auth(subs["owner"]),
    )
    assert response.json()["rationale"] == "Acta 12:\n\tpunto 3 aprobado."


# --- reading -------------------------------------------------------------------------------


def test_history_is_newest_first_and_readable_by_members(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser, member="member")
    path = reviews_url(org, manual["manual"])
    for status in ("pass", "fail"):
        review = passing(client, org, subs["owner"], manual["manual"], status=status)
        client.post(path, json=review, headers=auth(subs["owner"]))
    history = client.get(path, headers=auth(subs["member"]))
    assert history.status_code == 200
    assert [r["status"] for r in history.json()] == ["fail", "pass"]


def test_detail_shows_the_current_review_of_the_callers_org_only(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    other, others = org_with(client, superuser)
    path = reviews_url(org, manual["manual"])
    client.post(path, json=body(status="fail"), headers=auth(subs["owner"]))
    review = passing(client, org, subs["owner"], manual["manual"])
    client.post(path, json=review, headers=auth(subs["owner"]))

    def review(o: str, sub: str) -> object:
        detail = client.get(detail_url(o, manual["active"]), headers=auth(sub)).json()
        r2 = next(r for r in detail["requirements"] if r["code"] == "R2")
        return next(c for c in r2["controls"] if c["key"] == manual["manual"])["review"]

    current = review(org, subs["owner"])
    assert isinstance(current, dict)
    assert (current["status"], current["expired"]) == ("pass", False)
    assert review(other, others["owner"]) is None
    r1 = next(
        r
        for r in client.get(detail_url(org, manual["active"]), headers=auth(subs["owner"])).json()[
            "requirements"
        ]
        if r["code"] == "R1"
    )
    assert r1["controls"][0]["review"] is None  # automated control: never reviewed


def test_an_expired_review_is_shown_as_expired(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    client.post(
        reviews_url(org, manual["manual"]), json=body(status="fail"), headers=auth(subs["owner"])
    )
    with superuser.begin() as conn:  # time passes: the row is aged as superuser
        conn.execute(
            text(
                "UPDATE control_reviews SET valid_until = current_date - 1,"
                " reviewed_at = now() - interval '2 years' WHERE organization_id = :o"
            ),
            {"o": org},
        )
    detail = client.get(detail_url(org, manual["active"]), headers=auth(subs["owner"])).json()
    r2 = next(r for r in detail["requirements"] if r["code"] == "R2")
    assert r2["controls"][0]["review"]["expired"] is True


# --- table rules ---------------------------------------------------------------------------


INSERT = text(
    "INSERT INTO control_reviews (id, organization_id, control_key, status, rationale,"
    " valid_until, reviewed_by) VALUES (:id, :org, 'ctl.any', :status, :rationale,"
    " current_date + 30, :by) RETURNING id"
)


def insert(session: Session, **overrides: object) -> uuid.UUID:
    values = {
        "id": uuid.uuid4(),
        "org": ORG_A,
        "status": "pass",
        "rationale": "ok",
        "by": uuid.uuid4(),
        **overrides,
    }
    return uuid.UUID(str(session.execute(INSERT, values).scalar_one()))


@pytest.fixture
def tx(db_rollback: Session) -> Session:
    enter_org_context(db_rollback, ORG_A, ContextReason.MEMBERSHIP)
    return db_rollback


def test_reviews_are_append_only_for_the_app(tx: Session) -> None:
    review_id = insert(tx)
    for statement in (
        "UPDATE control_reviews SET status = 'fail' WHERE id = :id",
        "DELETE FROM control_reviews WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="permission denied"), tx.begin_nested():
            tx.execute(text(statement), {"id": review_id})


def test_rls_keeps_reviews_in_their_org(tx: Session) -> None:
    insert(tx)
    with pytest.raises(DBAPIError, match="row-level security"), tx.begin_nested():
        insert(tx, org=ORG_B)


@pytest.mark.parametrize(
    "overrides", [{"status": "manual"}, {"rationale": ""}, {"rationale": "x" * 2001}]
)
def test_checks_reject_bad_rows(tx: Session, overrides: dict[str, object]) -> None:
    with pytest.raises(DBAPIError, match="check constraint"), tx.begin_nested():
        insert(tx, **overrides)


def test_a_recorded_review_queues_a_rescore_of_its_org(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    client.post(
        reviews_url(org, manual["manual"]), json=body(status="fail"), headers=auth(subs["owner"])
    )
    with superuser.connect() as conn:
        queued = conn.execute(
            text(
                "SELECT task_name, queue_name, args FROM procrastinate_jobs"
                " WHERE args ->> 'organization_id' = :o"
                " AND queue_name <> 'notifications'"  # the org's daily notice chain
            ),
            {"o": org},
        ).all()
    assert [tuple(j) for j in queued] == [(RESCORE_TASK, "scans", {"organization_id": org})]


# --- citations (#262) ----------------------------------------------------------------------


def reviews_written(superuser: Engine, org: str) -> int:
    with superuser.connect() as conn:
        query = text("SELECT count(*) FROM control_reviews WHERE organization_id = :o")
        return int(conn.execute(query, {"o": org}).scalar_one())


def test_a_pass_must_cite_evidence_and_a_fail_need_not(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    path = reviews_url(org, manual["manual"])
    refused = client.post(path, json=body(), headers=auth(subs["owner"]))
    assert (refused.status_code, refused.json()["detail"]["code"]) == (
        422,
        "compliance.review_evidence_required",
    )
    assert reviews_written(superuser, org) == 0
    assert events(superuser, org, "control.reviewed") == 0
    failed = client.post(path, json=body(status="fail"), headers=auth(subs["owner"]))
    assert (failed.status_code, failed.json()["evidence"]) == (201, [])


@pytest.mark.parametrize("source", ["other_control", "other_org", "unknown"])
def test_only_evidence_of_this_control_in_this_org_can_be_cited(
    client: TestClient, superuser: Engine, manual: dict[str, str], source: str
) -> None:
    org, subs = org_with(client, superuser)
    other, others = org_with(client, superuser)
    cited = {
        "other_control": lambda: cite(client, org, subs["owner"], manual["control"]),
        "other_org": lambda: cite(client, other, others["owner"], manual["manual"]),
        "unknown": lambda: str(uuid.uuid4()),
    }[source]()
    response = client.post(
        reviews_url(org, manual["manual"]),
        json=body(evidence_ids=[cited]),
        headers=auth(subs["owner"]),
    )
    assert (response.status_code, response.json()["detail"]["code"]) == (
        422,
        "compliance.review_evidence_invalid",
    )
    assert reviews_written(superuser, org) == 0


def test_at_most_twenty_items_and_each_once(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    path = reviews_url(org, manual["manual"])
    many = [str(uuid.uuid4()) for _ in range(21)]
    too_many = client.post(path, json=body(evidence_ids=many), headers=auth(subs["owner"]))
    assert (too_many.status_code, too_many.json()["detail"]["code"]) == (422, "request.invalid")
    once = cite(client, org, subs["owner"], manual["manual"])
    review = client.post(path, json=body(evidence_ids=[once, once]), headers=auth(subs["owner"]))
    assert review.status_code == 201, review.text
    assert [e["id"] for e in review.json()["evidence"]] == [once]


def test_detail_history_and_dossier_show_what_a_review_cites(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser, member="member")
    path = reviews_url(org, manual["manual"])
    first = cite(client, org, subs["owner"], manual["manual"], title="Acta 12")
    second = cite(client, org, subs["owner"], manual["manual"], title="Política v3")
    recorded = client.post(
        path, json=body(evidence_ids=[first, second]), headers=auth(subs["owner"])
    )
    assert recorded.status_code == 201, recorded.text
    expected = {(first, "Acta 12"), (second, "Política v3")}

    def titles(review: dict) -> set[tuple[str, str]]:
        assert all(e["kind"] == "attestation" and e["collected_at"] for e in review["evidence"])
        return {(e["id"], e["title"]) for e in review["evidence"]}

    assert titles(recorded.json()) == expected
    history = client.get(path, headers=auth(subs["member"])).json()
    assert titles(history[0]) == expected
    detail = client.get(detail_url(org, manual["active"]), headers=auth(subs["member"])).json()
    r2 = next(r for r in detail["requirements"] if r["code"] == "R2")
    control = next(c for c in r2["controls"] if c["key"] == manual["manual"])
    assert titles(control["review"]) == expected
    dossier = client.get(
        f"/api/v1/orgs/{org}/frameworks/{manual['active']}/dossier", headers=auth(subs["owner"])
    )
    assert dossier.status_code == 200, dossier.text
    controls = [c for r in dossier.json()["requirements"] for c in r["controls"]]
    in_dossier = next(c for c in controls if c["key"] == manual["manual"])
    assert titles(in_dossier["review"]) == expected


def test_a_review_recorded_before_citations_reads_as_citing_none(
    client: TestClient, superuser: Engine, manual: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    with superuser.begin() as conn:  # a pass recorded before #262: no evidence_ids given
        conn.execute(
            text(
                "INSERT INTO control_reviews (id, organization_id, control_key, status,"
                " rationale, valid_until, reviewed_by) VALUES (gen_random_uuid(), :o, :c,"
                " 'pass', 'legacy', current_date + 30, gen_random_uuid())"
            ),
            {"o": org, "c": manual["manual"]},
        )
    detail = client.get(detail_url(org, manual["active"]), headers=auth(subs["owner"])).json()
    r2 = next(r for r in detail["requirements"] if r["code"] == "R2")
    review = next(c for c in r2["controls"] if c["key"] == manual["manual"])["review"]
    assert (review["status"], review["evidence"]) == ("pass", [])


def test_the_table_refuses_more_than_twenty_citations(tx: Session) -> None:
    ids = "{" + ",".join(str(uuid.uuid4()) for _ in range(21)) + "}"
    with pytest.raises(DBAPIError, match="check constraint"), tx.begin_nested():
        tx.execute(
            text(
                "INSERT INTO control_reviews (id, organization_id, control_key, status,"
                " rationale, valid_until, reviewed_by, evidence_ids) VALUES (:id, :org,"
                " 'ctl.any', 'pass', 'ok', current_date + 30, :by, CAST(:ids AS uuid[]))"
            ),
            {"id": uuid.uuid4(), "org": ORG_A, "by": uuid.uuid4(), "ids": ids},
        )
