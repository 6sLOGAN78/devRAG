import { PanelRight } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { HitView } from "@/services/retrieval-service";

export function HitCard({ hit, rank, reranked, onSource }: { hit: HitView; rank: number; reranked: boolean; onSource: (trigger: HTMLElement) => void }) {
  const { t, i18n } = useTranslation(), text = useRef<HTMLParagraphElement>(null);
  const [expanded, setExpanded] = useState(false), [long, setLong] = useState(false);
  useLayoutEffect(() => {
    if (expanded) return;
    const measure = () => { const element = text.current; setLong(element && element.clientHeight > 0 ? element.scrollHeight > element.clientHeight + 1 : hit.content.length > 600 || hit.content.split("\n").length > 6); };
    measure(); if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure); if (text.current) observer.observe(text.current); return () => observer.disconnect();
  }, [hit.content, expanded]);
  const number = new Intl.NumberFormat(i18n.language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const scores = { overall: hit.similarity, term: hit.termSimilarity, vector: hit.vectorSimilarity, rerank: hit.rerankSimilarity };
  return <Card data-testid="hit-card" data-chunk-id={hit.chunkId} data-rank={rank} className="grid gap-4 p-4">
    <header className="grid gap-1"><p className="text-xs font-semibold text-muted-foreground">{t("retrieval.hit.rank", { n: rank })}</p><h3 className="line-clamp-2 break-all text-base font-semibold">{hit.docName}</h3><div className="flex flex-wrap gap-1">{[...new Set(hit.positions.map((position) => position.page))].map((page) => <Badge variant="outline" key={page}>{t("chat.sources.page", { page })}</Badge>)}</div></header>
    <div><p ref={text} data-testid="hit-text" className={`whitespace-pre-wrap break-words text-base ${expanded ? "" : "line-clamp-6"}`}>{hit.content}</p>{long ? <Button type="button" variant="ghost" size="sm" data-testid="hit-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{t(expanded ? "retrieval.hit.less" : "retrieval.hit.more")}</Button> : null}</div>
    <dl className="flex flex-wrap gap-4">{(["overall", "term", "vector", ...(reranked ? ["rerank" as const] : [])] as const).map((key) => <div key={key} className={key === "overall" ? "min-w-40 flex-1" : undefined}>
      <dt className="text-xs font-semibold text-muted-foreground">{t(`retrieval.score.${key}`)}</dt><dd data-testid={`hit-score-${key}`} className="text-base font-semibold tabular-nums">{scores[key] !== null ? number.format(scores[key]!) : <><span aria-hidden="true">—</span><span className="sr-only">{t("retrieval.score.none")}</span></>}</dd>
      {key === "overall" ? <Progress value={(scores.overall ?? 0) * 100} valueText={scores.overall === null ? t("retrieval.score.none") : undefined} label={t("retrieval.score.overallLabel", { n: rank })} data-testid="hit-overall-bar" /> : null}
    </div>)}</dl>
    <Button type="button" variant="outline" size="sm" data-testid="hit-source" className="justify-self-start" onClick={(event) => onSource(event.currentTarget)}><PanelRight aria-hidden="true" />{t("retrieval.hit.source")}</Button>
  </Card>;
}
