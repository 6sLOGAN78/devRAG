import { useRef, useState, type MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useDefaultsRequest, useModelsRequest, useModelTenantId } from "@/hooks/use-llm-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { BlockedForm } from "./blocked-form";
import { CreateForm } from "./create-form";

export interface CreateDatasetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function FormSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="create-dataset-skeleton" className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>{t("datasets.form.createTitle")}</DialogTitle>
        <DialogDescription>{t("datasets.form.createBody")}</DialogDescription>
      </DialogHeader>
      <p role="status" className="sr-only">
        {t("datasets.form.loading")}
      </p>
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} className="h-10 w-full" aria-hidden="true" />
      ))}
    </div>
  );
}

type Decision = "form" | "blocked";

interface BodyProps {
  onClose: () => void;
  pendingRef: MutableRefObject<boolean>;
}

/**
 * Mounted only while the dialog is open, so its queries run and its form state lives exactly that long. The choice
 * between the form and the blocked form is made once, when the defaults and models first arrive: a later refetch (after
 * a "model no longer available" answer) keeps the form and its message instead of swapping it away (D-18).
 */
function Body({ onClose, pendingRef }: BodyProps) {
  const { t } = useTranslation();
  const workspace = useActiveWorkspace();
  const tenantId = useModelTenantId();
  const defaults = useDefaultsRequest();
  const models = useModelsRequest("embedding");
  const [decision, setDecision] = useState<Decision | null>(null);
  const canManage = workspace?.role === "owner" || workspace?.role === "admin";

  if (decision === null && defaults.data !== undefined && models.data !== undefined) {
    const saved = defaults.data.embedding;
    setDecision(saved !== "" && models.data.some((model) => model.id === saved && model.type === "embedding") ? "form" : "blocked");
  }

  if (decision === "blocked") return <BlockedForm canManage={canManage} onClose={onClose} />;
  if (decision === "form" && defaults.data !== undefined && models.data !== undefined && tenantId !== null) {
    return (
      <CreateForm
        tenantId={tenantId}
        workspaceName={workspace?.name ?? ""}
        models={models.data}
        defaultEmbedding={defaults.data.embedding}
        pendingRef={pendingRef}
        onClose={onClose}
        onBlocked={() => setDecision("blocked")}
      />
    );
  }
  if (defaults.isError || models.isError) {
    return (
      <div className="flex flex-col gap-4">
        <DialogHeader>
          <DialogTitle>{t("datasets.form.createTitle")}</DialogTitle>
        </DialogHeader>
        <ErrorState
          noun={t("models.errorNoun.settings")}
          onAction={() => {
            void defaults.refetch();
            void models.refetch();
          }}
        />
      </div>
    );
  }
  return <FormSkeleton />;
}

/**
 * Create dataset (UI-10, KB-01, KB-02, D-08, D-18). Opens in its normal form when the workspace has an explicit default
 * embedding model, and in its blocked form when it does not. Plan 03-25's settings dialog reuses `schemas.ts`,
 * `ServerFieldError` and `datasetErrorTarget`.
 */
export function CreateDatasetDialog({ open, onOpenChange }: CreateDatasetDialogProps) {
  const pendingRef = useRef(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="create-dataset-dialog"
        onEscapeKeyDown={(event) => {
          if (pendingRef.current) event.preventDefault();
        }}
        onInteractOutside={(event) => {
          if (pendingRef.current) event.preventDefault();
        }}
      >
        <Body onClose={() => onOpenChange(false)} pendingRef={pendingRef} />
      </DialogContent>
    </Dialog>
  );
}
