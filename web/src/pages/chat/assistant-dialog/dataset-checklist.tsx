import { useQuery } from "@tanstack/react-query";
import { Lock, Users } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Alert } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { DATASETS_PATH } from "@/constants/app-paths";
import { datasetsKeyRoot } from "@/hooks/use-knowledge-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { listDatasets, type DatasetView } from "@/services/dataset-service";
import { ApiError } from "@/services/http";

/** Fetch every visible page; a partial first page must not silently remove another checked binding. */
export function useAssistantDatasets(enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useQuery({
    queryKey: [...datasetsKeyRoot(tenantId), "assistant-options"], enabled: enabled && tenantId !== null, retry: false,
    queryFn: async ({ signal }) => {
      const rows: DatasetView[] = [];
      for (let page = 1; ; page += 1) {
        if (signal.aborted) throw new DOMException("Dataset option fetch aborted", "AbortError");
        const result = await listDatasets({ tenantId: tenantId!, page, pageSize: 100, keywords: "" });
        rows.push(...result.items);
        if (rows.length >= result.total) return rows;
        if (!result.items.length) throw new ApiError({ code: -1, status: 200, message: "The dataset list was incomplete." });
      }
    },
  });
}
interface Props {
  datasets: readonly Pick<DatasetView, "id" | "name" | "permission">[]; selected: readonly string[]; permission: "me" | "team";
  onToggle: (id: string, checked: boolean) => void; unavailableCount: number; flaggedIds?: readonly string[];
}
export function DatasetChecklist({ datasets, selected, permission, onToggle, unavailableCount, flaggedIds = [] }: Props) {
  const { t, i18n } = useTranslation(), base = useId();
  return <fieldset className="grid gap-2" data-testid="assistant-datasets">
    <legend className="mb-2 text-sm font-semibold">{t("assistant.field.datasets")}</legend>
    <p className="text-xs text-muted-foreground">{t("assistant.field.datasetsHelp")}</p>
    {unavailableCount > 0 ? <Alert variant="info" data-testid="assistant-datasets-unavailable">{t("assistant.datasets.skipped", { count: unavailableCount })}</Alert> : null}
    {!datasets.length ? <p className="text-sm text-muted-foreground">{t("assistant.datasets.none")} <Link className="text-foreground underline" to={DATASETS_PATH}>{t("assistant.datasets.link")}</Link></p> : null}
    <div className="max-h-48 overflow-y-auto">
      {[...datasets].sort((a, b) => a.name.localeCompare(b.name, i18n.language)).map((dataset) => {
        const privateRow = dataset.permission !== "team", disabled = permission === "team" && privateRow, id = `${base}-${dataset.id}`;
        return <div key={dataset.id} className="mb-2">
          <label htmlFor={id} data-testid="assistant-dataset-option" data-dataset-id={dataset.id} data-permission={dataset.permission} data-invalid={flaggedIds.includes(dataset.id) || undefined}
            className={`flex items-center gap-2 rounded border pr-3 ${flaggedIds.includes(dataset.id) ? "border-destructive" : "border-input"}`}>
            <Checkbox id={id} checked={selected.includes(dataset.id)} disabled={disabled} aria-label={dataset.name} aria-describedby={disabled ? `${id}-reason` : undefined} onChange={(checked) => onToggle(dataset.id, checked)} />
            <span className="min-w-0 flex-1 truncate text-sm" title={dataset.name}>{dataset.name}</span>
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">{privateRow ? <Lock className="size-3" aria-hidden="true" /> : <Users className="size-3" aria-hidden="true" />}{t(privateRow ? "assistant.visibility.meTitle" : "assistant.visibility.teamTitle")}</span>
          </label>
          {disabled ? <p id={`${id}-reason`} className="pl-10 text-xs text-muted-foreground">{t("assistant.datasets.privateReason")}</p> : null}
        </div>;
      })}
    </div>
  </fieldset>;
}
