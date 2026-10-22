import type { APIContext } from "astro";
import { alertas, meta, reais, TRATAMENTO, url } from "../lib/dados";

const esc = (t: string) =>
  t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function GET(context: APIContext) {
  const m = meta();
  const abs = (p: string) => new URL(url(p), context.site).toString();
  const itens = alertas().slice(0, 50);
  const entradas = itens
    .map((a) => {
      const link = abs(`alerta/${a.codigo}/`);
      const titulo = `${a.codigo}: ${TRATAMENTO[a.casa]} ${a.parlamentar_nome} — ${reais(a.valor)} (${a.regra_nome})`;
      return `  <entry>
    <id>${esc(link)}</id>
    <title>${esc(titulo)}</title>
    <link href="${esc(link)}"/>
    <updated>${a.criado_em}Z</updated>
    <summary>${esc(`${a.detalhe} ${m.aviso}`)}</summary>
  </entry>`;
    })
    .join("\n");
  const corpo = `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="pt-BR">
  <id>${esc(abs(""))}</id>
  <title>${esc(m.site.nome)}</title>
  <subtitle>${esc(m.aviso)}</subtitle>
  <link href="${esc(abs(""))}"/>
  <link rel="self" href="${esc(abs("atom.xml"))}"/>
  <updated>${new Date(m.atualizado_em).toISOString()}</updated>
  <author><name>${esc(m.site.nome)}</name></author>
${entradas}
</feed>
`;
  return new Response(corpo, { headers: { "Content-Type": "application/atom+xml; charset=utf-8" } });
}
