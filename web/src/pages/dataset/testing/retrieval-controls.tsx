import { Loader2, Search } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { LlmSelect } from "@/components/llm-select";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RangeField } from "@/components/ui/range-field";
import { Textarea } from "@/components/ui/textarea";
import type { ModelView } from "@/services/model-service";

export interface RetrievalValues { question: string; threshold: number; weight: number; rerankId: string }
interface Props {
  values: RetrievalValues; onChange: (values: RetrievalValues) => void; onReset: () => void; onRun: () => void; running: boolean;
  dirtyAfterRun?: boolean; models: readonly ModelView[]; questionError?: string;
}
export function RetrievalControls({ values, onChange, onReset, onRun, running, models, questionError }: Props) {
  const { t } = useTranslation(), id = useId(), input = useRef<HTMLTextAreaElement>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const error = validation ?? questionError, valid = values.question.trim() !== "" && values.question.length <= 2000;
  function run() {
    if (running) return;
    if (!valid) { setValidation(values.question.trim() === "" ? "errors.retrieval.questionRequired" : "errors.retrieval.questionMax"); input.current?.focus(); return; }
    setValidation(null); onRun();
  }
  return <Card className="h-fit p-6 lg:w-[360px] lg:shrink-0"><form noValidate data-testid="retrieval-controls" className="grid gap-6" onSubmit={(event) => { event.preventDefault(); run(); }}>
    <div className="grid gap-2"><Label htmlFor={`${id}-question`}>{t("retrieval.field.question")}</Label><Textarea ref={input} id={`${id}-question`} data-testid="field-retrieval-question" rows={3} className="max-h-40" placeholder={t("retrieval.field.questionPlaceholder")} value={values.question} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined}
      onChange={(event) => { setValidation(null); onChange({ ...values, question: event.target.value }); }} onKeyDown={(event) => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) { event.preventDefault(); run(); } }} />{error ? <p id={`${id}-error`} role="alert" className="text-xs text-destructive">{t(error)}</p> : null}</div>
    <RangeField id={`${id}-threshold`} label={t("retrieval.field.threshold")} value={values.threshold} onChange={(threshold) => onChange({ ...values, threshold })} min={0} max={1} step={0.05} readout={values.threshold.toFixed(2)} helper={t("retrieval.field.thresholdHelp")} lowLabel={t("assistant.field.thresholdLow")} highLabel={t("assistant.field.thresholdHigh")} testId="field-retrieval-threshold" />
    <RangeField id={`${id}-weight`} label={t("retrieval.field.weight")} value={values.weight} onChange={(weight) => onChange({ ...values, weight })} min={0} max={1} step={0.05} readout={t("assistant.field.weightValue", { keyword: Math.round((1 - values.weight) * 100), vector: Math.round(values.weight * 100) })} helper={t("retrieval.field.weightHelp")} lowLabel={t("assistant.field.weightLow")} highLabel={t("assistant.field.weightHigh")} testId="field-retrieval-weight" />
    <div className="grid gap-2"><Label htmlFor={`${id}-rerank`}>{t("retrieval.field.rerank")}</Label><LlmSelect id={`${id}-rerank`} data-testid="field-retrieval-rerank" type="rerank" models={models} value={values.rerankId} onChange={(rerankId) => onChange({ ...values, rerankId })} notSetLabel={t("assistant.field.rerankNone")} /><p className="text-xs text-muted-foreground">{t("retrieval.field.rerankHelp")}</p></div>
    <div className="flex flex-wrap justify-end gap-2"><Button type="button" variant="ghost" data-testid="retrieval-reset" onClick={() => { setValidation(null); onReset(); }}>{t("retrieval.reset")}</Button><Button type="submit" data-testid="retrieval-run" aria-disabled={running || !valid || undefined} aria-busy={running || undefined} className="aria-disabled:opacity-50">{running ? <Loader2 aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" /> : <Search aria-hidden="true" />}{t("retrieval.run")}</Button></div>
  </form></Card>;
}
