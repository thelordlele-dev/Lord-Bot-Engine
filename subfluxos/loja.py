import os
import logging
from datetime import datetime
import zoneinfo
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_API_KEY")
DATABASE_ID_LOJA = "2357a7a879af8065b815c6f88bc3c5bb"


def converter_para_minutos(valor_float):
    if valor_float is None:
        return None
    horas = int(valor_float)
    minutos = int(round((valor_float - horas) * 100))
    if minutos < 0 or minutos > 59 or horas < 0 or horas > 23:
        raise ValueError(f"Horário inválido: {valor_float}")
    return (horas * 60) + minutos


def verificar_status_loja(props_reais):
    chave_motivo = next(
        (k for k in props_reais.keys() if "motivo" in k.strip().lower()), None
    )
    motivo_personalizado_notion = "Estamos fechados no momento."
    if chave_motivo:
        if (
            "rich_text" in props_reais[chave_motivo]
            and props_reais[chave_motivo]["rich_text"]
        ):
            motivo_personalizado_notion = "".join(
                [
                    t.get("plain_text", "")
                    for t in props_reais[chave_motivo]["rich_text"]
                ]
            )

    chave_manual = next(
        (k for k in props_reais.keys() if k.strip().lower() == "status manual"), None
    )
    status_manual = "Auto"
    if chave_manual:
        info_coluna = props_reais[chave_manual]
        status_manual = (
            info_coluna.get("select", {}).get("name", "Auto")
            if "select" in info_coluna
            else info_coluna.get("status", {}).get("name", "Auto")
        )

    if status_manual == "Aberta":
        return {
            "aberta": True,
            "texto_notion": "Aberta",
            "motivo": "Forçado Manualmente",
        }
    elif status_manual == "Fechada":
        return {
            "aberta": False,
            "texto_notion": "Fechada",
            "motivo": motivo_personalizado_notion,
        }

    agora = datetime.now(zoneinfo.ZoneInfo("America/Sao_Paulo"))
    minutos_atual = (agora.hour * 60) + agora.minute

    for turno in [
        # Segunda a Sexta - Manhã
        {
            "dias": [1, 2, 3, 4, 5],
            "inicio": "Abertura - Manhã (Hora)",
            "fim": "Fechamento - Manhã (Hora)",
        },
        # Segunda a Sexta - Noite
        {
            "dias": [1, 2, 3, 4, 5],
            "inicio": "Abertura - Noite (Hora)",
            "fim": "Fechamento - Noite (Hora)",
        },
        # Fim de Semana - Manhã
        {
            "dias": [6, 7],
            "inicio": "Abertura - FS - Manhã (Hora)",
            "fim": "Fechamento - FS - Manhã (Hora)",
        },
        # Fim de Semana - Noite
        {
            "dias": [6, 7],
            "inicio": "Abertura - FS - Noite (Hora)",
            "fim": "Fechamento - FS - Noite (Hora)",
        },
    ]:
        if agora.isoweekday() in turno["dias"]:
            chave_inicio = next(
                (
                    k
                    for k in props_reais.keys()
                    if k.strip().lower() == turno["inicio"].lower()
                ),
                None,
            )
            chave_fim = next(
                (
                    k
                    for k in props_reais.keys()
                    if k.strip().lower() == turno["fim"].lower()
                ),
                None,
            )

            if chave_inicio and chave_fim:
                inicio_min = converter_para_minutos(
                    props_reais.get(chave_inicio, {}).get("number")
                )
                fim_min = converter_para_minutos(
                    props_reais.get(chave_fim, {}).get("number")
                )

                if inicio_min is not None and fim_min is not None:
                    aberto_neste_turno = (
                        (minutos_atual >= inicio_min) and (minutos_atual < fim_min)
                        if fim_min > inicio_min
                        else (minutos_atual >= inicio_min) or (minutos_atual < fim_min)
                    )
                    if aberto_neste_turno:
                        return {
                            "aberta": True,
                            "texto_notion": "Aberta",
                            "motivo": "Horário Regular Automático",
                        }

    return {
        "aberta": False,
        "texto_notion": "Fechada",
        "motivo": "⌚ Horário de Atendimento:\n\nde *Segunda à Sexta*,\ndas *11h às 15h*\ne das *18h às 23h*\n\nde *Sábado e Domingo*,\ndas *11h às 15h*\ne das *18h às 23h*",
    }


async def atualizar_painel_notion(page_id, status_texto):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    # Payload assuming it is a 'select' property
    payload = {"properties": {"Status Auto": {"select": {"name": status_texto}}}}

    async with httpx.AsyncClient() as client:
        resposta = await client.patch(url, headers=headers, json=payload)


async def obter_status_atual_loja():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID_LOJA}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resposta = await client.post(url, headers=headers)
        dados_notion = resposta.json()

    if not dados_notion.get("results"):
        return {
            "aberta": False,
            "motivo": "A tabela da Loja está vazia ou ID está incorreto.",
        }

    primeira_linha = dados_notion["results"][0]
    resultado = verificar_status_loja(primeira_linha["properties"])
    novo_status = resultado["texto_notion"]

    chave_auto = next(
        (
            k
            for k in primeira_linha["properties"].keys()
            if k.strip().lower() == "status auto"
        ),
        None,
    )
    status_visual_atual = ""
    if chave_auto:
        coluna_auto = primeira_linha["properties"][chave_auto]
        status_visual_atual = (
            coluna_auto.get("select", {}).get("name", "")
            if "select" in coluna_auto
            else coluna_auto.get("status", {}).get("name", "")
        )

    if novo_status != status_visual_atual:
        await atualizar_painel_notion(primeira_linha["id"], novo_status)

    return resultado
