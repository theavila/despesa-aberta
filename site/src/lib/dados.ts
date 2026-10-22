// Leitura dos JSONs exportados pelo pipeline (`serenata exportar`) e formatação.
import fs from "node:fs";
import path from "node:path";

export interface Resposta {
  alerta: string;
  recebida_em: string;
  autor: string;
  texto: string;
  documento: string | null;
}

export interface Alerta {
  codigo: string;
  regra_id: string;
  regra_nome: string;
  score: number;
  detalhe: string;
  criado_em: string;
  casa: "camara" | "senado";
  parlamentar: string;
  parlamentar_nome: string;
  partido: string | null;
  uf: string | null;
  data: string | null;
  competencia: string;
  categoria: string;
  fornecedor: string;
  fornecedor_nome: string;
  fornecedor_documento: string;
  valor: number;
  url_documento: string;
  fonte: string;
  respostas: Resposta[];
}

export interface Parlamentar {
  chave: string;
  casa: "camara" | "senado";
  id: string;
  nome: string;
  partido: string | null;
  uf: string | null;
  url_foto: string | null;
  despesas: number;
  total: number;
  por_categoria: { categoria: string; total: number }[];
  por_mes: { competencia: string; total: number }[];
  alertas: string[];
}

export interface Fornecedor {
  chave: string;
  nome: string;
  documento: string;
  despesas: number;
  parlamentares: number;
  total: number;
  alertas: string[];
}

export interface Regra {
  id: string;
  nome: string;
  descricao: string;
  parametros: Record<string, unknown>;
  arquivo: string;
  codigo_fonte: string;
}

export interface Meta {
  site: { nome: string; url: string };
  atualizado_em: string;
  aviso: string;
  despesas: number;
  valor_total: number;
  periodo: { inicio: string | null; fim: string | null };
  alertas_ativos: number;
  alertas_hoje: number;
  por_regra: Record<string, number>;
  parlamentares: number;
  respostas: number;
}

const cache = new Map<string, unknown>();

function ler<T>(nome: string): T {
  if (!cache.has(nome)) {
    const arquivo = path.join(process.cwd(), "src", "data", `${nome}.json`);
    cache.set(nome, JSON.parse(fs.readFileSync(arquivo, "utf-8")));
  }
  return cache.get(nome) as T;
}

export const meta = () => ler<Meta>("meta");
export const alertas = () => ler<Alerta[]>("alertas");
export const parlamentares = () => ler<Parlamentar[]>("parlamentares");
export const fornecedores = () => ler<Fornecedor[]>("fornecedores");
export const regras = () => ler<Regra[]>("regras");
export const respostas = () => ler<Resposta[]>("respostas");

export function alertasPorCodigo(): Map<string, Alerta> {
  return new Map(alertas().map((a) => [a.codigo, a]));
}

// ---- Endereços (o site é servido em um subcaminho, ex.: /serenata/) ----

export function url(caminho = ""): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  const limpo = caminho.replace(/^\//, "");
  return `${base}/${limpo}`;
}

export const urlAlerta = (codigo: string) => url(`alerta/${codigo}/`);
export const urlParlamentar = (chave: string) => url(`parlamentar/${chave}/`);
export const urlFornecedor = (chave: string) => url(`fornecedor/${chave}/`);

// ---- Formatação ----

const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const inteiro = new Intl.NumberFormat("pt-BR");
const compacto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });

export const reais = (v: number) => moeda.format(v);
export const numero = (v: number) => inteiro.format(v);
export const reaisCompacto = (v: number) => `R$ ${compacto.format(v)}`;

export function dataCurta(iso: string | null): string {
  if (!iso) return "sem data";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

const MESES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];
const DIAS = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];

export function dataPorExtenso(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split("-").map(Number);
  const dia = new Date(Date.UTC(a, m - 1, d)).getUTCDay();
  return `${DIAS[dia]}, ${d} de ${MESES[m - 1]} de ${a}`;
}

export function competenciaCurta(c: string): string {
  const [a, m] = c.split("-").map(Number);
  return `${MESES[m - 1].slice(0, 3)}/${String(a).slice(2)}`;
}

export function horario(iso: string): string {
  return iso.slice(11, 16).replace(":", "h");
}

export const CASAS = { camara: "Câmara", senado: "Senado" } as const;
export const TRATAMENTO = { camara: "Dep.", senado: "Sen." } as const;

export function filiacao(partido: string | null, uf: string | null): string {
  return [partido, uf].filter(Boolean).join("-");
}

// ---- Dados abertos por página ----

export function csv(linhas: Record<string, unknown>[]): string {
  if (!linhas.length) return "";
  const colunas = Object.keys(linhas[0]);
  const celula = (v: unknown) => {
    const t = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n;]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
  };
  return [colunas.join(","), ...linhas.map((l) => colunas.map((c) => celula(l[c])).join(","))].join("\n") + "\n";
}

export function alertaPlano(a: Alerta): Record<string, unknown> {
  const { respostas: _r, ...resto } = a;
  return { ...resto, respostas: a.respostas.length };
}
