import type { APIRoute } from "astro";
import { alertaPlano, alertasPorCodigo, csv, type Fornecedor, fornecedores } from "../../lib/dados";

export function getStaticPaths() {
  return fornecedores().map((f) => ({ params: { chave: f.chave }, props: { f } }));
}

export const GET: APIRoute = ({ props }) => {
  const { f } = props as { f: Fornecedor };
  const porCodigo = alertasPorCodigo();
  return new Response(csv(f.alertas.map((c) => alertaPlano(porCodigo.get(c)!))), {
    headers: { "Content-Type": "text/csv; charset=utf-8" },
  });
};
