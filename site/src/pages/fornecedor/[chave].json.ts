import type { APIRoute } from "astro";
import { alertasPorCodigo, type Fornecedor, fornecedores } from "../../lib/dados";

export function getStaticPaths() {
  return fornecedores().map((f) => ({ params: { chave: f.chave }, props: { f } }));
}

export const GET: APIRoute = ({ props }) => {
  const { f } = props as { f: Fornecedor };
  const porCodigo = alertasPorCodigo();
  return new Response(JSON.stringify({ ...f, alertas: f.alertas.map((c) => porCodigo.get(c)) }, null, 1), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
};
