"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useAccessReview, useCloseReview, useDecide } from "@/lib/api/routines";
import { type Membership, orgAccessReviews, orgHome } from "@/lib/org";
import { canReviewControls, isContributor } from "@/lib/permissions";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { PageHeader, Panel } from "./page-frame";

/** One access review: decide keep or revoke per account, then close it (recorded-routines spec). */
export function AccessReviewView({ org, reviewId }: { org: Membership; reviewId: string }) {
  const t = useTranslations("routines.access");
  const format = useFormatter();
  const query = useAccessReview(org.organization_id, reviewId);
  const decide = useDecide(org.organization_id, reviewId);
  const close = useCloseReview(org.organization_id, reviewId);
  const crumbs = [{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title"), href: orgAccessReviews(org.organization_id) }];
  if (query.isPending) return <><PageHeader crumbs={crumbs} title={t("title")} /><p role="status">{t("loading")}</p></>;
  if (query.isError) return <><PageHeader crumbs={crumbs} title={t("title")} /><ErrorMessage error={query.error} /></>;
  const review = query.data;
  const open = review.closed_at === null;
  const canDecide = open && isContributor(org.role);
  return <div className="panel-grid">
    <PageHeader crumbs={[...crumbs, { label: review.title }]} title={review.title}
      description={<>{review.system} · {t("decided", { decided: review.total - review.pending, total: review.total })}</>}
      actions={open && canReviewControls(org.role)
        ? <button type="button" className="button-primary" disabled={review.pending > 0 || close.isPending} onClick={() => close.mutate()}
          title={review.pending > 0 ? t("closeBlocked", { count: review.pending }) : undefined}>{t("close")}</button>
        : review.closed_at ? <span className="badge" data-severity="done"><Icon name="done" />{t("closedOn", { date: format.dateTime(new Date(review.closed_at), { dateStyle: "medium" }) })}</span> : null} />
    {open && review.pending > 0 ? <p className="text-sm text-muted">{t("closeBlocked", { count: review.pending })}</p> : null}
    {decide.isError ? <ErrorMessage error={decide.error} /> : null}
    {close.isError ? <ErrorMessage error={close.error} /> : null}
    {close.isSuccess ? <p role="status" className="notice"><Icon name="done" />{t("closedEvidence")}</p> : null}
    <Panel title={t("accounts")}>
      <div className="table-region" role="region" aria-label={t("accounts")} tabIndex={0}><table className="w-full text-left">
        <thead><tr><th scope="col">{t("account")}</th><th scope="col">{t("decision")}</th></tr></thead>
        <tbody>{review.entries.map((e) => <tr key={e.id}>
          <td>{e.account}{e.detail ? <span className="block text-sm text-muted">{e.detail}</span> : null}</td>
          <td>{canDecide
            ? <div role="group" aria-label={t("decisionFor", { account: e.account })} className="decision-group">
              {(["keep", "revoke"] as const).map((d) => <button key={d} type="button" className="dashboard-button" aria-pressed={e.decision === d}
                disabled={decide.isPending} onClick={() => decide.mutate({ entry_id: e.id, decision: d, note: "" })}>{t(d)}</button>)}
            </div>
            : e.decision ? t(e.decision) : <span className="text-muted">{t("pending")}</span>}</td>
        </tr>)}</tbody>
      </table></div>
    </Panel>
  </div>;
}
