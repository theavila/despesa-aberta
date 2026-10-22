import type { APIRoute } from "astro";
import { alertaPlano, alertas, csv } from "../../lib/dados";

export const GET: APIRoute = () =>
  new Response(csv(alertas().map(alertaPlano)), {
    headers: { "Content-Type": "text/csv; charset=utf-8" },
  });
