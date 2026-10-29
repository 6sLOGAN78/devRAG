import { useRef, type MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { SETTINGS_MODES } from "@/constants/failure-codes";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocumentDetailRequest } from "@/hooks/use-document-request";
import { useDatasetRequest } from "@/hooks/use-knowledge-request";
import { DEFAULT_CHUNK_TOKEN_NUM, DEFAULT_DELIMITER, DEFAULT_OVERLAPPED_PERCENT } from "@/services/dataset-service";
import { ChunkMethodForm, type ChunkSettings, type ChunkTarget } from "./chunk-method-form";

export type { ChunkTarget } from "./chunk-method-form";

export interface ChunkMethodDialogProps {
  /** What the dialog edits. Kept by the owner after closing so the dialog can fade out; `null` before the first opening. */
  target: ChunkTarget | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Where focus goes when the dialog has closed. There is no trigger, so the owner decides. */
  onCloseAutoFocus?: (event: Event) => void;
}

function Header({ target }: { target: ChunkTarget }) {
  const { t } = useTranslation();
  return (
    <DialogHeader>
      <DialogTitle>{target.mode === SETTINGS_MODES.document ? t("datasets.chunking.titleDocument", { name: target.name }) : t("datasets.chunking.titleDataset")}</DialogTitle>
      <DialogDescription>{target.mode === SETTINGS_MODES.document ? t("datasets.chunking.bodyDocument") : t("datasets.chunking.bodyDataset")}</DialogDescription>
    </DialogHeader>
  );
}

const positive = (value: number, fallback: number): number => (value > 0 ? value : fallback);

function Body({ target, pendingRef, onClose }: { target: ChunkTarget; pendingRef: MutableRefObject<boolean>; onClose: () => void }) {
  const { t } = useTranslation();
  const isDocument = target.mode === SETTINGS_MODES.document;
  const document = useDocumentDetailRequest(target.datasetId, isDocument ? target.documentId : undefined, isDocument);
  const dataset = useDatasetRequest(isDocument ? undefined : target.datasetId);
  let settings: ChunkSettings | undefined;
  if (document.data !== undefined && isDocument) {
    const detail = document.data;
    settings = {
      parserId: detail.parserId,
      chunkTokenNum: positive(detail.chunkTokenNum, DEFAULT_CHUNK_TOKEN_NUM),
      delimiter: detail.delimiter === "" ? DEFAULT_DELIMITER : detail.delimiter,
      overlappedPercent: detail.overlappedPercent > 0 ? detail.overlappedPercent : DEFAULT_OVERLAPPED_PERCENT,
      chunkCount: detail.chunkCount,
      run: detail.run,
      pages: detail.pages,
      layoutRecognize: detail.layoutRecognize,
      resumeModel:detail.resumeModel,
      resumeUseModel:detail.resumeUseModel,
      asrModel:detail.asrModel,
      audioLanguage:detail.audioLanguage,
      imageModel:detail.imageModel,
      pictureOcrOnly:detail.pictureOcrOnly,
    };
  } else if (dataset.data !== undefined && !isDocument) {
    const detail = dataset.data;
    settings = {
      parserId: detail.parserId,
      chunkTokenNum: detail.parserConfig.chunkTokenNum,
      delimiter: detail.parserConfig.delimiter,
      overlappedPercent: detail.parserConfig.overlappedPercent,
      chunkCount: 0,
      run: "0",
      pages: detail.parserConfig.pages,
      layoutRecognize: detail.parserConfig.layoutRecognize,
      resumeModel:detail.parserConfig.resumeModel,
      resumeUseModel:detail.parserConfig.resumeUseModel,
      asrModel:detail.parserConfig.asrModel,
      audioLanguage:detail.parserConfig.audioLanguage,
      imageModel:detail.parserConfig.imageModel,
      pictureOcrOnly:detail.parserConfig.pictureOcrOnly,
    };
  }
  const query = isDocument ? document : dataset;
  if (settings !== undefined) return <ChunkMethodForm target={target} settings={settings} pendingRef={pendingRef} onClose={onClose} />;
  if (query.isError) {
    return (
      <div className="flex flex-col gap-4">
        <Header target={target} />
        <ErrorState heading={t("datasets.chunking.error.loadHeading")} onAction={() => void query.refetch()} />
      </div>
    );
  }
  return (
    <div data-testid="chunk-method-skeleton" className="flex flex-col gap-4">
      <Header target={target} />
      <p role="status" className="sr-only">
        {t("datasets.chunking.loading")}
      </p>
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} className="h-10 w-full" aria-hidden="true" />
      ))}
    </div>
  );
}

/**
 * Chunking method and parser settings (UI-13, UI-14 in part, D-15, D-27), for one document or as the dataset default.
 * Only General can be chosen; the other seven methods are shown as unavailable. The body is mounted only while open and
 * keyed by its target, so every opening starts from the stored settings with no earlier error (FE-04). The owner draws
 * the control that opens it only for callers who may change the document or manage the dataset.
 */
export function ChunkMethodDialog({ target, open, onOpenChange, onCloseAutoFocus }: ChunkMethodDialogProps) {
  const pendingRef = useRef(false);
  const key = target === null ? "" : target.mode === SETTINGS_MODES.document ? `${target.mode}:${target.documentId}` : `${target.mode}:${target.datasetId}`;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="chunk-method-dialog"
        className="max-h-[90vh] max-w-xl overflow-y-auto"
        onCloseAutoFocus={onCloseAutoFocus}
        onEscapeKeyDown={(event) => {
          if (pendingRef.current) event.preventDefault();
        }}
        onInteractOutside={(event) => {
          if (pendingRef.current) event.preventDefault();
        }}
      >
        {target !== null ? <Body key={key} target={target} pendingRef={pendingRef} onClose={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}
