import { parserBackendsPath } from "@/constants/api-paths";
import { request } from "./http";

export type ExternalPdfBackend = "docling" | "mineru";

/** A finite client-side copy of the server's operator-configured names. */
export async function listExternalPdfBackends(): Promise<ExternalPdfBackend[]> {
  const raw = await request<unknown>({ url: parserBackendsPath, method: "GET" }, { silent: true });
  const data = typeof raw === "object" && raw !== null ? raw as Record<string, unknown> : {};
  const names = Array.isArray(data.available) ? data.available : [];
  return (["docling", "mineru"] as const).filter((name) => names.includes(name));
}
