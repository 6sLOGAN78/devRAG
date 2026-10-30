import {useModelsRequest} from "@/hooks/use-llm-request";
import {useWatch} from "react-hook-form";
import {LlmSelect} from "@/components/llm-select";
import type { Control } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { ServerFieldError } from "@/components/create-dataset-dialog/server-field-error";
import { CHUNK_SIZE_MAX, CHUNK_SIZE_MIN, OVERLAP_MAX, OVERLAP_MIN } from "@/constants/chunk-methods";
import type { ChunkFormInput, ParseConfigField } from "./schema";

export interface ParseConfigurationProps {
  control: Control<ChunkFormInput>;
  disabled?: boolean;
  wholeDocument?: boolean;
  questionAnswer?: boolean;
  book?: boolean;
  paper?: boolean;
  laws?: boolean;
  presentation?: boolean;
  table?: boolean;
  picture?: boolean;
  audio?: boolean;
  email?: boolean;
  resume?: boolean;
  tag?: boolean;
  /** A refusal placed by the server under one field: the finished sentence, shown as a text node. */
  answers?: Partial<Record<ParseConfigField, string>>;
  /** Called when the reader edits a field, so its server answer can be cleared. */
  onEdit?: (field: ParseConfigField) => void;
}

function PictureFields({control,disabled}:{control:Control<ChunkFormInput>;disabled:boolean}) {
  const {t}=useTranslation();
  const visionModels=useModelsRequest("vision");
  const ocrOnly=useWatch({control,name:"pictureOcrOnly"});
  return (
    <>
        <p data-testid="picture-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.pictureSettings")}</p>
        <FormField control={control} name="pictureOcrOnly" render={({field})=><FormItem><FormLabel>{t("datasets.chunking.pictureOcrOnly")}</FormLabel><FormControl><input type="checkbox" data-testid="field-picture-ocr-only" checked={field.value ?? false} disabled={disabled} onChange={e=>field.onChange(e.target.checked)}/></FormControl></FormItem>}/>
        <FormField control={control} name="imageModel" render={({field})=><FormItem><FormLabel>{t("datasets.chunking.imageModel")}</FormLabel><FormControl><LlmSelect type="vision" data-testid="field-image-model" models={visionModels.data ?? []} value={field.value ?? ""} onChange={field.onChange} disabled={disabled || ocrOnly}/></FormControl></FormItem>}/>
    </>
  );
}

function ResumeFields({control,disabled}:{control:Control<ChunkFormInput>;disabled:boolean}) {
  const {t}=useTranslation();
  const models=useModelsRequest("chat");
  const infer=useWatch({control,name:"resumeUseModel"});
  return <>
    <p data-testid="resume-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.resumeSettings")}</p>
    <FormField control={control} name="resumeUseModel" render={({field})=><FormItem><FormLabel>{t("datasets.chunking.resumeUseModel")}</FormLabel><FormControl><input type="checkbox" data-testid="field-resume-use-model" checked={field.value ?? false} disabled={disabled} onChange={e=>field.onChange(e.target.checked)}/></FormControl><FormMessage/></FormItem>}/>
    <FormField control={control} name="resumeModel" render={({field})=><FormItem><FormLabel>{t("datasets.chunking.resumeModel")}</FormLabel><FormControl><LlmSelect type="chat" models={models.data ?? []} value={field.value ?? ""} onChange={field.onChange} disabled={disabled || !infer} data-testid="field-resume-model"/></FormControl><FormMessage/></FormItem>}/>
  </>;
}

function AudioFields({control,disabled}:{control:Control<ChunkFormInput>;disabled:boolean}) {
  const {t}=useTranslation();
  const models=useModelsRequest("asr");
  return <>
    <p data-testid="audio-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.audioSettings")}</p>
    <FormField control={control} name="asrModel" render={({field})=><FormItem><FormLabel>{t("datasets.chunking.asrModel")}</FormLabel><FormControl><LlmSelect type="asr" models={models.data ?? []} value={field.value ?? ""} onChange={field.onChange} disabled={disabled} data-testid="field-asr-model"/></FormControl><FormMessage/></FormItem>}/>
    <FormField control={control} name="audioLanguage" render={({field})=><FormItem><FormLabel>{t("datasets.chunking.audioLanguage")}</FormLabel><FormControl><Input {...field} value={field.value ?? ""} disabled={disabled} data-testid="field-audio-language" maxLength={3}/></FormControl><FormDescription>{t("datasets.chunking.audioLanguageHelp")}</FormDescription><FormMessage/></FormItem>}/>
  </>;
}

/**
 * The settings of the General method: chunk size, delimiters and overlap, then the read-only "Not available yet" rows.
 * The delimiter field shows and takes `\n` and `\t` as typed text; the schema turns them into real characters.
 */
export function ParseConfiguration({ control, disabled = false, wholeDocument = false, questionAnswer = false, book = false, paper = false, laws = false, presentation = false, table = false, picture = false, audio = false, email = false, resume = false, tag = false, answers = {}, onEdit }: ParseConfigurationProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <FormField control={control} name="layoutRecognize" render={({ field }) => (
        <FormItem>
          <div className="flex min-h-10 items-center gap-3">
            <FormControl>
              <input type="checkbox" checked={field.value !== false} disabled={disabled} data-testid="field-layout"
                className="h-5 w-5 accent-primary" ref={field.ref} name={field.name} onBlur={field.onBlur}
                onChange={(event) => { onEdit?.("layoutRecognize"); field.onChange(event.target.checked); }} />
            </FormControl>
            <FormLabel>{t("datasets.chunking.field.layout")}</FormLabel>
          </div>
          <FormDescription>{t("datasets.chunking.field.layoutHelp")}</FormDescription>
          <FormMessage /><ServerFieldError text={answers.layoutRecognize ?? null} />
        </FormItem>
      )} />
      <FormField control={control} name="pageRanges" render={({ field }) => (
        <FormItem>
          <FormLabel>{t("datasets.chunking.field.pages")}</FormLabel>
          <FormControl><Input {...field} value={field.value ?? ""} disabled={disabled} maxLength={1024}
            data-testid="field-page-ranges" onChange={(event) => { onEdit?.("pageRanges"); field.onChange(event); }} /></FormControl>
          <FormDescription>{t("datasets.chunking.field.pagesHelp")}</FormDescription>
          <FormMessage /><ServerFieldError text={answers.pageRanges ?? null} />
        </FormItem>
      )} />
      {resume ? <ResumeFields control={control} disabled={disabled}/> : null}
      {tag ? <p data-testid="tag-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.tagSettings")}</p> : null}
      {email ? <p data-testid="email-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.emailSettings")}</p> : null}
      {audio ? <AudioFields control={control} disabled={disabled}/> : null}
      {picture ? <PictureFields control={control} disabled={disabled}/> : null}
      {table ? <p data-testid="table-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.tableSettings")}</p> : null}
      {presentation ? <p data-testid="presentation-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.presentationSettings")}</p> : null}
      {laws ? <p data-testid="laws-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.lawsSettings")}</p> : null}
      {paper ? <p data-testid="paper-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.paperSettings")}</p> : null}
      {book ? <p data-testid="book-settings-note" className="text-sm text-muted-foreground">{t("datasets.chunking.bookSettings")}</p> : null}
      {questionAnswer ? <p data-testid="qa-pair-settings" className="text-sm text-muted-foreground">{t("datasets.chunking.qaSettings")}</p> : null}
      {wholeDocument ? <p data-testid="one-document-settings" className="text-sm text-muted-foreground">{t("datasets.chunking.oneSettings")}</p> : null}
      <FormField
        control={control}
        name="chunkSize"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t("datasets.chunking.field.size")}</FormLabel>
            <FormControl>
              <Input
                {...field}
                type="number"
                inputMode="numeric"
                min={CHUNK_SIZE_MIN}
                max={CHUNK_SIZE_MAX}
                step={1}
                disabled={disabled || wholeDocument || questionAnswer || picture || audio}
                data-testid="field-chunk-size"
                onChange={(event) => {
                  onEdit?.("chunkSize");
                  field.onChange(event);
                }}
              />
            </FormControl>
            <FormDescription>{t("datasets.chunking.field.sizeHelp")}</FormDescription>
            <FormMessage />
            <ServerFieldError text={answers.chunkSize ?? null} />
          </FormItem>
        )}
      />
      <FormField
        control={control}
        name="delimiters"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t("datasets.chunking.field.delimiters")}</FormLabel>
            <FormControl>
              <Input
                {...field}
                autoComplete="off"
                spellCheck={false}
                disabled={disabled || wholeDocument || questionAnswer || book || paper || laws || presentation || table || picture || audio || email || resume || tag}
                data-testid="field-delimiters"
                className="font-mono"
                onChange={(event) => {
                  onEdit?.("delimiters");
                  field.onChange(event);
                }}
              />
            </FormControl>
            <FormDescription>{t("datasets.chunking.field.delimitersHelp")}</FormDescription>
            <FormMessage />
            <ServerFieldError text={answers.delimiters ?? null} />
          </FormItem>
        )}
      />
      <FormField
        control={control}
        name="overlap"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t("datasets.chunking.field.overlap")}</FormLabel>
            <FormControl>
              <Input
                {...field}
                type="number"
                inputMode="numeric"
                min={OVERLAP_MIN}
                max={OVERLAP_MAX}
                step={1}
                disabled={disabled || wholeDocument || questionAnswer || book || paper || laws || presentation || table || picture || audio || email || resume || tag}
                data-testid="field-overlap"
                onChange={(event) => {
                  onEdit?.("overlap");
                  field.onChange(event);
                }}
              />
            </FormControl>
            <FormDescription>{t("datasets.chunking.field.overlapHelp")}</FormDescription>
            <FormMessage />
            <ServerFieldError text={answers.overlap ?? null} />
          </FormItem>
        )}
      />
      <FormField control={control} name="autoKeywords" render={({field}) => <FormItem>
        <FormLabel>{t("datasets.chunking.field.autoKeywords")}</FormLabel>
        <FormControl><Input {...field} value={field.value ?? 0} type="number" inputMode="numeric" min={0} max={32} step={1} disabled={disabled} data-testid="field-auto-keywords" onChange={event=>{onEdit?.("autoKeywords");field.onChange(event);}} /></FormControl>
        <FormDescription>{t("datasets.chunking.field.autoKeywordsHelp")}</FormDescription><FormMessage/><ServerFieldError text={answers.autoKeywords ?? null}/>
      </FormItem>}/>
      <FormField control={control} name="autoQuestions" render={({field}) => <FormItem>
        <FormLabel>{t("datasets.chunking.field.autoQuestions")}</FormLabel>
        <FormControl><Input {...field} value={field.value ?? 0} type="number" inputMode="numeric" min={0} max={16} step={1} disabled={disabled} data-testid="field-auto-questions" onChange={event=>{onEdit?.("autoQuestions");field.onChange(event);}} /></FormControl>
        <FormDescription>{t("datasets.chunking.field.autoQuestionsHelp")}</FormDescription><FormMessage/><ServerFieldError text={answers.autoQuestions ?? null}/>
      </FormItem>}/>
    </div>
  );
}
