import type { APIRoute } from "astro";
import { alertas } from "../../lib/dados";

export const GET: APIRoute = () =>
  new Response(JSON.stringify(alertas()), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
