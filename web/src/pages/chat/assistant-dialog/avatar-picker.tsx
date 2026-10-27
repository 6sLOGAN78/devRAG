import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { AvatarInitials } from "@/components/avatar-initials";
import { Label } from "@/components/ui/label";

function safePicture(value: string): boolean {
  return value.length <= 400000 && /^data:image\/(?:png|jpeg);base64,[A-Za-z0-9+/]+={0,2}$/.test(value);
}
export async function readAvatar(file: File): Promise<string> {
  if (!["image/png", "image/jpeg"].includes(file.type)) throw new Error("assistant.picture.type");
  if (file.size > 1048576) throw new Error("assistant.picture.size");
  const image = await createImageBitmap(file);
  try {
    if (image.width < 1 || image.height < 1) throw new Error("assistant.picture.read");
    const canvas = document.createElement("canvas"); canvas.width = 128; canvas.height = 128;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("assistant.picture.read");
    const side = Math.min(image.width, image.height);
    context.drawImage(image, (image.width - side) / 2, (image.height - side) / 2, side, side, 0, 0, 128, 128);
    const result = canvas.toDataURL("image/png");
    if (!safePicture(result)) throw new Error("assistant.picture.read");
    return result;
  } finally { image.close(); }
}
export function AvatarPicker({ name = "", value, onChange, disabled, onBusyChange }: { name?: string; value: string; onChange: (value: string) => void; disabled?: boolean; onBusyChange?: (busy: boolean) => void }) {
  const { t } = useTranslation(), id = useId();
  const input = useRef<HTMLInputElement>(null), generation = useRef(0);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => () => { generation.current += 1; }, []);
  const select = async (file: File) => {
    const current = ++generation.current; setError(""); setBusy(true); onBusyChange?.(true);
    try { const image = await readAvatar(file); if (generation.current === current) onChange(image); }
    catch (error) {
      if (generation.current === current) setError(error instanceof Error && ["assistant.picture.type", "assistant.picture.size"].includes(error.message) ? error.message : "assistant.picture.read");
    } finally { if (generation.current === current) { setBusy(false); onBusyChange?.(false); } }
  };
  return <div className="grid gap-2" aria-busy={busy || undefined}>
    <Label htmlFor={id}>{t("assistant.field.picture")}</Label>
    <p className="text-xs text-muted-foreground">{t("assistant.field.pictureHelp")}</p>
    <div className="flex items-center gap-4">
      <span className="inline-flex size-16 items-center justify-center overflow-hidden rounded-full bg-muted" data-testid="assistant-avatar-preview">
        <AvatarInitials avatar={safePicture(value) ? value : ""} nickname={name} email="" size="lg" />
      </span>
      <input ref={input} id={id} type="file" hidden accept="image/png,image/jpeg" data-testid="assistant-avatar-input" disabled={disabled || busy}
        onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void select(file); }} />
      <Button type="button" variant="outline" data-testid="assistant-avatar-choose" disabled={disabled || busy} onClick={() => input.current?.click()}>{t("assistant.picture.choose")}</Button>
      {value ? <Button type="button" variant="ghost" data-testid="assistant-avatar-remove" disabled={disabled || busy} onClick={() => { generation.current += 1; setError(""); onChange(""); }}>{t("assistant.picture.remove")}</Button> : null}
    </div>
    {error ? <p role="alert" data-testid="assistant-avatar-error" className="text-sm text-destructive">{t(error)}</p> : null}
  </div>;
}
