import { useTranslation } from "react-i18next";
import type { TurnState } from "@/services/chat-turn";
export function LiveRegion({ state }: { state: TurnState }) {
  const { t } = useTranslation();
  const key = state.status === "finished" ? "finished" : state.status === "stopped" ? "stopped" : state.status === "failed" ? "failed" : state.status === "streaming" && state.text ? "started" : null;
  return <div data-testid="chat-live" role="status" aria-live="polite" className="sr-only">{key ? t(`chat.live.${key}`) : ""}</div>;
}
