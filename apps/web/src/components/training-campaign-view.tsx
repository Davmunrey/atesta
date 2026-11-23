"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useCloseTraining, useTrainingCampaign } from "@/lib/api/routines";
import { type Membership, orgHome, orgTraining } from "@/lib/org";
import { canReviewControls } from "@/lib/permissions";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { PageHeader, Panel } from "./page-frame";
import { CampaignState } from "./training-view";

/** One training: who confirmed, and closing it into evidence (recorded-routines spec). */
export function TrainingCampaignView({ org, campaignId }: { org: Membership; campaignId: string }) {
  const t = useTranslations("routines.training");
  const format = useFormatter();
  const query = useTrainingCampaign(org.organization_id, campaignId);
  const close = useCloseTraining(org.organization_id, campaignId);
  const crumbs = [{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title"), href: orgTraining(org.organization_id) }];
  if (query.isPending) return <><PageHeader crumbs={crumbs} title={t("title")} /><p role="status">{t("loading")}</p></>;
  if (query.isError) return <><PageHeader crumbs={crumbs} title={t("title")} /><ErrorMessage error={query.error} /></>;
  const campaign = query.data;
  const open = campaign.closed_at === null;
  return <div className="panel-grid">
    <PageHeader crumbs={[...crumbs, { label: campaign.title }]} title={campaign.title}
      description={<><a href={campaign.material_url} className="text-link underline" rel="noopener noreferrer" target="_blank">{t("openMaterial")}</a> · {t("count", { count: campaign.acknowledged })}</>}
      actions={open && canReviewControls(org.role)
        ? <button type="button" className="button-primary" disabled={close.isPending} onClick={() => close.mutate()}>{t("close")}</button>
        : <CampaignState campaign={campaign} />} />
    {close.isError ? <ErrorMessage error={close.error} /> : null}
    {close.isSuccess ? <p role="status" className="notice"><Icon name="done" />{t("closedEvidence")}</p> : null}
    <Panel title={t("people")}>
      {campaign.acknowledgements.length === 0 ? <p className="text-muted">{t("nobody")}</p>
        : <div className="table-region" role="region" aria-label={t("people")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("name")}</th><th scope="col">{t("email")}</th><th scope="col">{t("when")}</th></tr></thead>
          <tbody>{campaign.acknowledgements.map((a) => <tr key={a.email}>
            <td>{a.full_name}</td><td className="break-all">{a.email}</td>
            <td className="tabular-nums">{format.dateTime(new Date(a.acknowledged_at), { dateStyle: "medium", timeStyle: "short" })}</td>
          </tr>)}</tbody>
        </table></div>}
    </Panel>
  </div>;
}
