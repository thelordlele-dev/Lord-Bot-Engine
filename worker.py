import os
import json
import asyncio
import httpx
import aio_pika
from dotenv import load_dotenv

from config.database import obter_conexao, db_pool

# ========================================================
# IMPORTAÇÃO DOS SUBFLUXOS DO SISTEMA THELORDTRUFAS
# ========================================================
from subfluxos.adiciona_itens import processar_adiciona_itens
from subfluxos.adiciona_mais_itens import roteia_adicionar_mais_itens
from subfluxos.aguardando_categoria import processar_aguardando_categoria
from subfluxos.aguardando_escolha_item import processar_escolha_item
from subfluxos.ajuda_e_atendimento import (
    processar_ajuda_pedido,
    processar_retorno_pos_ajuda,
)
from subfluxos.alteracao_itens import processar_alteracao_itens
from subfluxos.atendimento_expirado import processar_sessoes_expiradas
from subfluxos.atualiza_promocao import processar_atualizacao_promocoes
from subfluxos.cadastra_avaliacao_atendimento import (
    processar_cadastro_avaliacao_atendimento,
)
from subfluxos.cadastra_avaliacao_pedido import processar_cadastro_avaliacao
from subfluxos.cadastra_endereco import processar_cadastro_endereco
from subfluxos.cadastra_nome import processar_cadastro_nome
from subfluxos.calculo_pedido import processar_calculo_pedido
from subfluxos.cardapio import processar_busca_cardapio
from subfluxos.cliente_existe import executar_fluxo_cliente_existe
from subfluxos.cliente_retorna_menu import processar_retorno_menu
from subfluxos.cria_pagamento import processar_criacao_pagamento
from subfluxos.envia_avaliacao_pedido import processar_envio_avaliacao
from subfluxos.existe_cupom import processar_existe_cupom
from subfluxos.expirou_pagamento import processar_pagamentos_expirados
from subfluxos.finaliza_pedido import processar_finalizacao_pedido
from subfluxos.gerenciador_encerramento import processar_encerramento_sessao
from subfluxos.loja import obter_status_atual_loja
from subfluxos.menu_alternativo import processar_menu_alternativo
from subfluxos.menu_inicio import processar_menu_inicio
from subfluxos.navegacao_cardapio import processar_navegacao_cardapio
from subfluxos.pagamento_efetuado import processar_pagamento_efetuado
from subfluxos.primeiro_contato import gerar_mensagem_boas_vindas
from subfluxos.processa_alteração_itens import processando_alteracao_itens
from subfluxos.processa_pedido import processar_pedido
from subfluxos.processar_lista_itens import processar_quantidade_item
from subfluxos.recuperar_vendas import processar_recuperacao_vendas
from subfluxos.retorna_bot_pagamento import processar_retorno_bot_pagamento
from subfluxos.status_pedido import processar_status_pagamento
from subfluxos.validade_giftback import verificar_e_expirar_cupons
from subfluxos.verifica_cupom import processar_verificacao_cupom
from subfluxos.visualizando_carrinho import processar_visualizacao_carrinho

load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "https://graph.facebook.com/v26.0")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
NOTION_TOKEN = os.getenv("NOTION_API_KEY", "")


async def disparar_whatsapp(payload: dict):
    """Envia o payload de resposta para a API da Meta (WhatsApp)."""
    if not payload:
        return
    url = f"{WHATSAPP_API_URL}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            print(f"Resposta Meta WhatsApp: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Erro ao disparar mensagem para o WhatsApp: {e}")


async def executar_resultado_background(resultado, conexao):
    """Lê os comandos SQL e payloads das rotinas de background e executa-os de facto!"""
    if not resultado:
        return

    # Se a rotina retornar uma lista de clientes (ex: 5 clientes expiraram ao mesmo tempo)
    if isinstance(resultado, list):
        for res in resultado:
            await executar_resultado_background(res, conexao)
        return

    if isinstance(resultado, dict):
        # 1. Executar os comandos SQL no PostgreSQL
        sql_cmds = (
            resultado.get("sql_update")
            or resultado.get("sql_updates")
            or resultado.get("sql_reseta")
        )
        if sql_cmds:
            if isinstance(sql_cmds, str):
                sql_cmds = [sql_cmds]
            async with conexao.transaction():
                for sql in sql_cmds:
                    if sql and sql.strip():
                        await conexao.execute(sql)

        # 2. Disparar Mensagens no WhatsApp
        payload_final = (
            resultado.get("payload")
            or resultado.get("payload_whatsapp")
            or resultado.get("payload_flow")
        )
        mensagens_multiplas = resultado.get("mensagens_multiplas", [])

        if mensagens_multiplas:
            for msg in mensagens_multiplas:
                payload_base = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                }
                payload_base.update(msg)
                await disparar_whatsapp(payload_base)
        else:
            if not payload_final and "messaging_product" in resultado:
                payload_final = resultado

            if payload_final:
                await disparar_whatsapp(payload_final)


async def processar_maquina_estados(
    jid: str, telefone_real: str, primeiro_nome: str, entrada_cliente: str
):
    """
    Motor central da máquina de estados com injeção automática de dependências e contexto unificado.
    """
    conexao = await obter_conexao()
    if not conexao:
        print(
            f"Erro crítico: Não foi possível obter conexão com o PostgreSQL para o JID {jid}"
        )
        return

    is_bot_paused = False

    try:
        # 1. Busca padrão pelo JID
        row = await conexao.fetchrow(
            "SELECT jid, estado_conversa, carrinho_json, mapa_id_json, categoria_selecionada, pagina_atual, primeiro_nome, is_bot_paused FROM conversas_bot WHERE jid = $1",
            jid,
        )

        # 2. RECUPERAÇÃO MÁGICA: Fallback para Webhooks do Chatwoot
        # O Chatwoot manda o telefone no lugar do JID. Se não achar o JID, procura pelo telefone_real.
        if not row and telefone_real:
            row = await conexao.fetchrow(
                "SELECT jid, estado_conversa, carrinho_json, mapa_id_json, categoria_selecionada, pagina_atual, primeiro_nome, is_bot_paused FROM conversas_bot WHERE telefone_real = $1 LIMIT 1",
                telefone_real,
            )
            if row:
                jid = row[
                    "jid"
                ]  # Substitui o JID falso pelo JID verdadeiro da Meta (BR...)!

        # 3. Se realmente não existir, cria o novo cliente
        if not row:
            print(
                f">>> [NOVO CLIENTE] Inserindo JID {jid} e Telefone {telefone_real} no banco..."
            )
            await conexao.execute(
                "INSERT INTO conversas_bot (jid, telefone_real, estado_conversa, ultima_interacao) VALUES ($1, $2, 'primeiro_contato', NOW()) ON CONFLICT (jid) DO NOTHING",
                jid,
                telefone_real,
            )
            cliente_db = {"estado_conversa": "primeiro_contato"}
            estado_atual = "primeiro_contato"
            is_bot_paused = False
        else:
            cliente_db = dict(row)
            estado_atual = cliente_db.get("estado_conversa")
            is_bot_paused = bool(cliente_db.get("is_bot_paused", False))
            if cliente_db.get("primeiro_nome"):
                primeiro_nome = cliente_db.get("primeiro_nome")

        # ----------------------------------------------------
        # ⏱️ RELÓGIO MESTRE: Atualiza o tempo sempre que o cliente enviar mensagem!
        # ----------------------------------------------------
        await conexao.execute(
            "UPDATE conversas_bot SET ultima_interacao = NOW() WHERE jid = $1", jid
        )

    except Exception as e:
        print(f"Erro ao consultar base de dados para o JID {jid}: {e}")
        # Retirado o db_pool.release() daqui! A devolução da conexão acontece no finally.
        return

    resultado = None

    # ----------------------------------------------------
    # INTERCETORES DE COMANDOS INTERNOS E FORMULÁRIOS (FLOWS)
    # ----------------------------------------------------
    eh_formulario = False
    formulario_dict = {}

    if isinstance(entrada_cliente, str):
        if entrada_cliente == "/retorno_ajuda":
            estado_atual = "retorno_pos_ajuda"

        elif entrada_cliente.startswith("/retorno_frete|||"):
            estado_atual = "retorna_bot_pagamento"
            json_chatwoot = entrada_cliente.split("|||")[1]
            cliente_db["payload_chatwoot"] = json.loads(json_chatwoot)

        elif entrada_cliente.startswith("/pedido_finalizado|||"):
            estado_atual = "finaliza_pedido"
            num_pedido_extraido = entrada_cliente.split("|||")[1]
            cliente_db["numero_pedido"] = num_pedido_extraido

        elif "flow_token" in entrada_cliente:
            try:
                formulario_dict = json.loads(entrada_cliente)
                eh_formulario = True
            except Exception:
                pass
    elif isinstance(entrada_cliente, dict) and "flow_token" in entrada_cliente:
        formulario_dict = entrada_cliente
        eh_formulario = True

    # ----------------------------------------------------
    # TRAVA DE BOT PAUSADO / ATENDIMENTO HUMANO EM ANDAMENTO
    # ----------------------------------------------------
    # Se o bot está pausado ou no estado 'ajuda_pedido', e NÃO é um comando do sistema
    # (como /retorno_ajuda, /retorno_frete ou /pedido_finalizado), o bot morre em SILÊNCIO.
    if (is_bot_paused or estado_atual == "ajuda_pedido") and estado_atual not in [
        "retorno_pos_ajuda",
        "retorna_bot_pagamento",
        "finaliza_pedido",
    ]:
        print(
            f"🤫 [BOT PAUSADO] Cliente {jid} em atendimento humano. Ignorando mensagem do usuário."
        )
        # Retirado o db_pool.release() daqui! A devolução da conexão acontece no finally.
        return
    # ----------------------------------------------------

    # ROTEAMENTO GLOBAL DE FORMULÁRIOS (O seu Switch do n8n)
    if eh_formulario:
        if estado_atual == "cliente_existe":
            formulario_dict["Jid"] = jid

            if (
                "screen_0_Escolha_a_opo_1" in formulario_dict
                or "screen_0_Escolha_a_opo_0" in formulario_dict
            ):
                resultado = await processar_cadastro_avaliacao_atendimento(
                    formulario_dict, conexao
                )
            elif "screen_0_D_sua_nota_0" in formulario_dict:
                resultado = await processar_cadastro_avaliacao(formulario_dict, conexao)
            elif "screen_0_Nome_Nome_Social_0" in formulario_dict:
                nome = formulario_dict.get("screen_0_Nome_Nome_Social_0", "").strip()
                primeiro = nome.split()[0].upper() if nome else "CLIENTE"
                resultado = {
                    "sql_update": f"UPDATE conversas_bot SET nome_cliente = '{nome}', primeiro_nome = '{primeiro}' WHERE jid = '{jid}';"
                }
            elif "screen_0_Endereo_0" in formulario_dict:
                endereco = formulario_dict.get("screen_0_Endereo_0", "").strip()
                bairro = formulario_dict.get("screen_0_Bairro_1", "").strip()
                resultado = {
                    "sql_update": f"UPDATE conversas_bot SET endereco = '{endereco}', bairro = '{bairro}' WHERE jid = '{jid}';"
                }
            else:
                resultado = {"sql_update": None}

            estado_atual = "ignorar_mensagem"

            if isinstance(resultado, dict):
                resultado.pop("payload", None)
                resultado.pop("payload_whatsapp", None)
                resultado.pop("payload_flow", None)
                resultado.pop("mensagens_multiplas", None)

        else:
            if "screen_0_Nome_Nome_Social_0" in formulario_dict:
                estado_atual = "primeiro_contato"
            elif "screen_0_Endereo_0" in formulario_dict:
                estado_atual = "cadastra_endereco"
            elif (
                "screen_0_Escolha_a_opo_1" in formulario_dict
                or "screen_0_Escolha_a_opo_0" in formulario_dict
            ):
                estado_atual = "aguardando_avaliacao_atendimento"
                cliente_db["form_data"] = formulario_dict
            elif "screen_0_D_sua_nota_0" in formulario_dict:
                estado_atual = "aguardando_avaliacao"
                cliente_db["form_data"] = formulario_dict

    notion_headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    whatsapp_api_config = {
        "WHATSAPP_PHONE_NUMBER_ID": WHATSAPP_PHONE_NUMBER_ID,
        "token": WHATSAPP_ACCESS_TOKEN,
        "url": WHATSAPP_API_URL,
    }
    chatwoot_headers = {"api_access_token": os.getenv("CHATWOOT_TOKEN", "")}

    try:
        if estado_atual == "ignorar_mensagem":
            pass

        elif not estado_atual or estado_atual in ["primeiro_contato", "inicio"]:
            if eh_formulario:
                resultado = processar_cadastro_nome(
                    dados_formulario=formulario_dict,
                    user_id=jid,
                    telefone_real=telefone_real,
                    db_connection=conexao,
                    notion_headers=notion_headers,
                    whatsapp_api_config=whatsapp_api_config,
                )
            else:
                resultado = gerar_mensagem_boas_vindas(jid, telefone_real)

        elif estado_atual == "cliente_existe":
            resultado = executar_fluxo_cliente_existe(jid, primeiro_nome)

        elif estado_atual == "menu_inicio":
            if str(entrada_cliente) == "3":
                resultado = await processar_ajuda_pedido(
                    jid, telefone_real, primeiro_nome, cliente_db
                )
            else:
                resultado = processar_menu_inicio(
                    jid, jid, primeiro_nome, entrada_cliente, cliente_db
                )
        elif estado_atual == "menu_alternativo":
            if str(entrada_cliente) == "3":
                # No menu alternativo, a opção 3 é SAIR.
                carrinho_salvo = cliente_db.get("carrinho_json", "[]")
                resultado = processar_encerramento_sessao(
                    jid, telefone_real, primeiro_nome, carrinho_salvo, "sair"
                )
            else:
                resultado = processar_menu_alternativo(
                    jid, jid, primeiro_nome, entrada_cliente, cliente_db
                )

        elif estado_atual == "aguardando_categoria":
            resultado = processar_aguardando_categoria(
                jid, jid, primeiro_nome, entrada_cliente, cliente_db
            )
        elif estado_atual and estado_atual.startswith("visualizando_cardapio"):
            resultado = processar_navegacao_cardapio(
                estado_atual,
                jid,
                jid,
                primeiro_nome,
                entrada_cliente,
                cliente_db,
            )
        elif estado_atual == "aguardando_escolha_item":
            resultado = processar_escolha_item(
                jid, jid, primeiro_nome, entrada_cliente, cliente_db
            )
        elif estado_atual == "processando_lista_itens":
            resultado = processar_quantidade_item(
                jid, jid, primeiro_nome, entrada_cliente, cliente_db
            )
        elif estado_atual == "calcula_pedido":
            resultado = processar_calculo_pedido(jid, jid, primeiro_nome, cliente_db)
        elif estado_atual in ["visualizando_carrinho", "menu_carrinho"]:
            resultado = processar_visualizacao_carrinho(
                jid, jid, primeiro_nome, entrada_cliente, cliente_db
            )
        elif estado_atual == "aguardando_alteracao_item":
            resultado = processar_alteracao_itens(
                jid, jid, primeiro_nome, entrada_cliente, cliente_db
            )
        elif estado_atual == "processando_alteracao_itens":
            resultado = processando_alteracao_itens(
                jid, jid, entrada_cliente, cliente_db
            )
        elif estado_atual == "existe_cupom":
            resultado = processar_existe_cupom(
                jid, jid, primeiro_nome, entrada_cliente, cliente_db
            )
        elif estado_atual in ["verifica_cupom", "tenta_cupom"]:
            resultado = processar_verificacao_cupom(
                jid, jid, primeiro_nome, entrada_cliente, cliente_db, {}
            )
        elif estado_atual in [
            "adiciona_itens_frete",
            "adiciona_itens_cupom",
            "adiciona_mais_itens",
        ]:
            resultado = roteia_adicionar_mais_itens(
                jid, telefone_real, primeiro_nome, entrada_cliente, cliente_db
            )
        elif estado_atual == "adiciona_itens":
            resultado = processar_adiciona_itens(
                jid, jid, primeiro_nome, entrada_cliente, cliente_db
            )
        elif estado_atual == "cadastra_endereco":
            resultado = processar_cadastro_endereco(
                jid, jid, entrada_cliente, cliente_db
            )
        elif estado_atual in ["finalizando_pedido", "processa_pedido"]:
            resultado = processar_pedido(
                cliente_db, entrada_cliente, conexao, chatwoot_headers
            )
        elif estado_atual == "finaliza_pedido":
            resultado = await processar_finalizacao_pedido(
                {
                    "numero_pedido": cliente_db.get("numero_pedido"),
                    "telefone_real": telefone_real,
                },
                conexao,
            )
        elif estado_atual == "cria_pagamento":
            resultado = processar_criacao_pagamento(jid, jid, primeiro_nome, cliente_db)
        elif estado_atual == "pagamento_efetuado":
            resultado = processar_pagamento_efetuado(
                {
                    "numero_pedido": cliente_db.get("numero_pedido", ""),
                    "telefone_real": jid,
                },
                conexao,
            )
        elif estado_atual == "status_pedido":
            resultado = processar_status_pagamento(
                {}, cliente_db, conexao, chatwoot_headers
            )
        elif estado_atual == "retorna_bot_pagamento":
            payload_chatwoot = cliente_db.get("payload_chatwoot", {})
            resultado = await processar_retorno_bot_pagamento(payload_chatwoot, conexao)

        elif estado_atual == "aguardando_avaliacao_atendimento":
            form_data = cliente_db.get("form_data", {})
            if form_data:
                form_data["Jid"] = jid
                resultado = await processar_cadastro_avaliacao_atendimento(
                    form_data, conexao
                )
            else:
                resultado = await processar_cadastro_avaliacao_atendimento(
                    {
                        "Jid": jid,
                        "screen_0_Escolha_a_opo_0": "Sim",
                        "screen_0_Escolha_a_opo_1": entrada_cliente,
                    },
                    conexao,
                )

        elif estado_atual == "aguardando_avaliacao":
            form_data = cliente_db.get("form_data", {})
            if form_data:
                form_data["Jid"] = jid
                resultado = await processar_cadastro_avaliacao(form_data, conexao)
            else:
                resultado = await processar_cadastro_avaliacao(
                    {"Jid": jid, "screen_0_D_sua_nota_0": entrada_cliente}, conexao
                )

        elif estado_atual == "envia_avaliacao_pedido":
            resultado = processar_envio_avaliacao(jid, jid, cliente_db)
        elif estado_atual in ["encerrado", "cliente_sair"]:
            carrinho_salvo = cliente_db.get("carrinho_json", "[]")
            resultado = processar_encerramento_sessao(
                jid, telefone_real, primeiro_nome, carrinho_salvo, "sair"
            )
        elif estado_atual == "retorna_menu":
            resultado = processar_retorno_menu(jid, jid, cliente_db)
        elif estado_atual in ["ajuda_pedido", "ajuda_e_atendimento"]:
            # Se cair aqui e não tiver sido barrado pela trava acima, não faz nada
            pass
        elif estado_atual == "retorno_pos_ajuda":
            resultado = await processar_retorno_pos_ajuda(
                jid, telefone_real, primeiro_nome, cliente_db
            )
        else:
            print(f"Estado '{estado_atual}' não reconhecido para o JID {jid}")
            return

        if asyncio.iscoroutine(resultado):
            resultado = await resultado

        if isinstance(resultado, dict):
            sql_cmds = (
                resultado.get("sql_update")
                or resultado.get("sql_updates")
                or resultado.get("sql_reseta")
            )

            if sql_cmds:
                if isinstance(sql_cmds, str):
                    sql_cmds = [sql_cmds]

                async with conexao.transaction():
                    for sql in sql_cmds:
                        if sql and sql.strip():
                            await conexao.execute(sql)

            destinatario_final = telefone_real if telefone_real else jid

            payload_final = (
                resultado.get("payload")
                or resultado.get("payload_whatsapp")
                or resultado.get("payload_flow")
            )

            mensagens_multiplas = resultado.get("mensagens_multiplas", [])

            if mensagens_multiplas:
                for msg in mensagens_multiplas:
                    payload_base = {
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                    }
                    payload_base.update(msg)
                    payload_base["to"] = destinatario_final

                    await disparar_whatsapp(payload_base)
            else:
                if not payload_final and "messaging_product" in resultado:
                    payload_final = resultado

                if payload_final:
                    payload_final["to"] = destinatario_final
                    await disparar_whatsapp(payload_final)

    except Exception as e:
        print(f"Erro ao processar máquina de estados para JID {jid}: {e}")
    finally:
        if db_pool:
            await db_pool.release(conexao)


# ========================================================
# ROTINAS AUTOMÁTICAS EM BACKGROUND
# ========================================================


async def loop_sessoes_expiradas():
    """Limpa sessões expiradas em background periodicamente."""
    while True:
        try:
            print("A limpar sessões e atendimentos expirados...")
            conexao = await obter_conexao()
            try:
                notion_headers = {"Authorization": f"Bearer {NOTION_TOKEN}"}
                chatwoot_headers = {"api_access_token": os.getenv("CHATWOOT_TOKEN", "")}
                whatsapp_config = {
                    "url": WHATSAPP_API_URL,
                    "phone_id": WHATSAPP_PHONE_NUMBER_ID,
                    "token": WHATSAPP_ACCESS_TOKEN,
                }

                if asyncio.iscoroutinefunction(processar_sessoes_expiradas):
                    resultado = await processar_sessoes_expiradas(
                        db_connection=conexao,
                        notion_headers=notion_headers,
                        chatwoot_headers=chatwoot_headers,
                        whatsapp_api_config=whatsapp_config,
                    )
                else:
                    resultado = processar_sessoes_expiradas(
                        db_connection=conexao,
                        notion_headers=notion_headers,
                        chatwoot_headers=chatwoot_headers,
                        whatsapp_api_config=whatsapp_config,
                    )

                # 🚀 MAGIA DA TRANSIÇÃO DO BACKGROUND: Executa SQL e envia o Zap!
                await executar_resultado_background(resultado, conexao)

            finally:
                if db_pool:
                    await db_pool.release(conexao)
        except Exception as e:
            print(f"Erro no loop de sessões expiradas: {e}")

        # Reduzido para 1 minuto (60s) para uma resposta precisa
        await asyncio.sleep(60)


async def loop_pagamento_expirado():
    """Verifica pagamentos expirados em background."""
    while True:
        try:
            print("A verificar pagamentos expirados...")
            conexao = await obter_conexao()
            try:
                notion_headers = {"Authorization": f"Bearer {NOTION_TOKEN}"}
                chatwoot_headers = {"api_access_token": os.getenv("CHATWOOT_TOKEN", "")}
                whatsapp_config = {
                    "url": WHATSAPP_API_URL,
                    "phone_id": WHATSAPP_PHONE_NUMBER_ID,
                    "token": WHATSAPP_ACCESS_TOKEN,
                }
                if asyncio.iscoroutinefunction(processar_pagamentos_expirados):
                    resultado = await processar_pagamentos_expirados(
                        db_connection=conexao,
                        notion_headers=notion_headers,
                        chatwoot_headers=chatwoot_headers,
                        whatsapp_api_config=whatsapp_config,
                    )
                else:
                    resultado = processar_pagamentos_expirados(
                        db_connection=conexao,
                        notion_headers=notion_headers,
                        chatwoot_headers=chatwoot_headers,
                        whatsapp_api_config=whatsapp_config,
                    )

                # 🚀 MAGIA DA TRANSIÇÃO
                await executar_resultado_background(resultado, conexao)

            finally:
                if db_pool:
                    await db_pool.release(conexao)
        except Exception as e:
            print(f"Erro no loop de pagamento_expirado: {e}")

        await asyncio.sleep(60)


async def loop_validade_giftback():
    """Valida e expira cupons periodicamente em background."""
    while True:
        try:
            print("A verificar validade de cupons e giftbacks...")
            conexao = await obter_conexao()
            try:
                if asyncio.iscoroutinefunction(verificar_e_expirar_cupons):
                    resultado = await verificar_e_expirar_cupons(db_connection=conexao)
                else:
                    resultado = verificar_e_expirar_cupons(db_connection=conexao)

                print(f"Resultado da limpeza de cupons: {resultado}")
            finally:
                if db_pool:
                    await db_pool.release(conexao)
        except Exception as e:
            print(f"Erro no loop de validade de cupons: {e}")

        # Roda a cada 1 hora (3600 segundos), igual ao Schedule Trigger do n8n
        await asyncio.sleep(3600)


async def loop_atualiza_promocoes():
    while True:
        try:
            print("A verificar validade de promoções...")
            # Chame aqui a sua função de processamento de promoções
            await processar_atualizacao_promocoes()
        except Exception as e:
            print(f"Erro no loop de atualização de promoções: {e}")
        await asyncio.sleep(43200)  # A cada 12 horas


async def loop_status_loja():
    while True:
        try:
            print("A verificar status da loja...")
            # Chame aqui a sua função de processamento de promoções
            await obter_status_atual_loja()
        except Exception as e:
            print(f"Erro no loop de verificar status da loja: {e}")
        await asyncio.sleep(300)  # A cada 5 minutos


async def main():
    """Inicia o worker conectando-se e escutando as filas do RabbitMQ."""
    print("Iniciando Worker Enterprise com suporte completo aos 42 subfluxos...")

    asyncio.create_task(loop_sessoes_expiradas())
    asyncio.create_task(loop_pagamento_expirado())
    asyncio.create_task(loop_validade_giftback())
    asyncio.create_task(loop_atualiza_promocoes())
    asyncio.create_task(loop_status_loja())

    connection = await aio_pika.connect_robust(RABBITMQ_URL)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=20)

        fila_whatsapp = await channel.declare_queue(
            "novos_pedidos", durable=True, arguments={"x-queue-type": "quorum"}
        )
        await channel.declare_queue(
            "pagamento_efetuado", durable=True, arguments={"x-queue-type": "quorum"}
        )
        await channel.declare_queue(
            "cria_pagamento", durable=True, arguments={"x-queue-type": "quorum"}
        )
        await channel.declare_queue(
            "finaliza_pedido", durable=True, arguments={"x-queue-type": "quorum"}
        )
        await channel.declare_queue(
            "status_pedido", durable=True, arguments={"x-queue-type": "quorum"}
        )
        await channel.declare_queue(
            "retorna_bot", durable=True, arguments={"x-queue-type": "quorum"}
        )

        print("Worker a escutar todas as filas com sucesso!")

        async with fila_whatsapp.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        dados = json.loads(message.body.decode())
                        print(
                            f">>> [RABBITMQ] Mensagem nova recebida na fila! Dados: {dados}"
                        )

                        jid = dados.get("jid")
                        telefone_real = dados.get("telefone_real", jid)
                        primeiro_nome = dados.get("primeiro_nome", "Cliente")
                        entrada_cliente = dados.get("entrada_cliente", "")

                        await processar_maquina_estados(
                            jid, telefone_real, primeiro_nome, entrada_cliente
                        )
                    except Exception as e:
                        print(
                            f"Erro ao processar mensagem na fila 'novos_pedidos': {e}"
                        )


if __name__ == "__main__":
    asyncio.run(main())


# import os
# import json
# import asyncio
# import httpx
# import aio_pika
# import traceback
# from dotenv import load_dotenv

# from config.database import obter_conexao, db_pool

# # ========================================================
# # IMPORTAÇÃO DOS SUBFLUXOS DO SISTEMA THELORDTRUFAS
# # ========================================================
# from subfluxos.adiciona_itens import processar_adiciona_itens
# from subfluxos.adiciona_mais_itens import roteia_adicionar_mais_itens
# from subfluxos.aguardando_categoria import processar_aguardando_categoria
# from subfluxos.aguardando_escolha_item import processar_escolha_item
# from subfluxos.ajuda_e_atendimento import processar_ajuda_pedido, processar_retorno_pos_ajuda
# from subfluxos.alteracao_itens import processar_alteracao_itens
# from subfluxos.atendimento_expirado import processar_sessoes_expiradas
# from subfluxos.atualiza_promocao import processar_atualizacao_promocoes
# from subfluxos.cadastra_avaliacao_atendimento import processar_cadastro_avaliacao_atendimento
# from subfluxos.cadastra_avaliacao_pedido import processar_cadastro_avaliacao
# from subfluxos.cadastra_endereco import processar_cadastro_endereco
# from subfluxos.cadastra_nome import processar_cadastro_nome
# from subfluxos.calculo_pedido import processar_calculo_pedido
# from subfluxos.cardapio import processar_busca_cardapio
# from subfluxos.cliente_existe import executar_fluxo_cliente_existe
# from subfluxos.cliente_retorna_menu import processar_retorno_menu
# from subfluxos.cria_pagamento import processar_criacao_pagamento
# from subfluxos.envia_avaliacao_pedido import processar_envio_avaliacao
# from subfluxos.existe_cupom import processar_existe_cupom
# from subfluxos.expirou_pagamento import processar_pagamentos_expirados
# from subfluxos.finaliza_pedido import processar_finalizacao_pedido
# from subfluxos.gerenciador_encerramento import processar_encerramento_sessao
# from subfluxos.loja import verificar_status_loja
# from subfluxos.menu_alternativo import processar_menu_alternativo
# from subfluxos.menu_inicio import processar_menu_inicio
# from subfluxos.navegacao_cardapio import processar_navegacao_cardapio
# from subfluxos.pagamento_efetuado import processar_pagamento_efetuado
# from subfluxos.primeiro_contato import gerar_mensagem_boas_vindas
# from subfluxos.processa_alteração_itens import processando_alteracao_itens
# from subfluxos.processa_pedido import processar_pedido
# from subfluxos.processar_lista_itens import processar_quantidade_item
# from subfluxos.recuperar_vendas import processar_recuperacao_vendas
# from subfluxos.retorna_bot_pagamento import processar_retorno_bot_pagamento
# from subfluxos.status_pedido import processar_status_pagamento
# from subfluxos.validade_giftback import verificar_e_expirar_cupons
# from subfluxos.verifica_cupom import processar_verificacao_cupom
# from subfluxos.visualizando_carrinho import processar_visualizacao_carrinho

# load_dotenv()

# RABBITMQ_URL = os.getenv("RABBITMQ_URL")
# WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "https://graph.facebook.com/v26.0")
# WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
# WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
# NOTION_TOKEN = os.getenv("NOTION_API_KEY", "")

# async def disparar_whatsapp(payload: dict):
#     """Envia o payload de resposta para a API da Meta (WhatsApp)."""
#     if not payload:
#         return
#     url = f"{WHATSAPP_API_URL}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
#     headers = {
#         "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
#         "Content-Type": "application/json",
#     }
#     async with httpx.AsyncClient() as client:
#         try:
#             response = await client.post(url, headers=headers, json=payload)
#             print(f"Resposta Meta WhatsApp: {response.status_code} - {response.text}")
#         except Exception as e:
#             print(f"Erro ao disparar mensagem para o WhatsApp: {e}")

# async def executar_resultado_background(resultado, conexao):
#     if not resultado:
#         return
#     if isinstance(resultado, list):
#         for res in resultado:
#             await executar_resultado_background(res, conexao)
#         return

#     if isinstance(resultado, dict):
#         sql_cmds = resultado.get("sql_update") or resultado.get("sql_updates") or resultado.get("sql_reseta")
#         if sql_cmds:
#             if isinstance(sql_cmds, str):
#                 sql_cmds = [sql_cmds]
#             async with conexao.transaction():
#                 for sql in sql_cmds:
#                     if sql and sql.strip():
#                         await conexao.execute(sql)

#         payload_final = resultado.get("payload") or resultado.get("payload_whatsapp") or resultado.get("payload_flow")
#         mensagens_multiplas = resultado.get("mensagens_multiplas", [])

#         if mensagens_multiplas:
#             for msg in mensagens_multiplas:
#                 payload_base = {"messaging_product": "whatsapp", "recipient_type": "individual"}
#                 payload_base.update(msg)
#                 await disparar_whatsapp(payload_base)
#         else:
#             if not payload_final and "messaging_product" in resultado:
#                 payload_final = resultado
#             if payload_final:
#                 await disparar_whatsapp(payload_final)

# async def processar_maquina_estados(jid: str, telefone_real: str, primeiro_nome: str, entrada_cliente: str):
#     conexao = await obter_conexao()
#     if not conexao:
#         print(f"Erro crítico: Não foi possível obter conexão com o PostgreSQL para o JID {jid}")
#         return

#     try:
#         is_bot_paused = False

#         row = await conexao.fetchrow(
#             "SELECT jid, estado_conversa, carrinho_json, mapa_id_json, categoria_selecionada, pagina_atual, primeiro_nome, is_bot_paused FROM conversas_bot WHERE jid = $1",
#             jid,
#         )

#         if not row and telefone_real:
#             row = await conexao.fetchrow(
#                 "SELECT jid, estado_conversa, carrinho_json, mapa_id_json, categoria_selecionada, pagina_atual, primeiro_nome, is_bot_paused FROM conversas_bot WHERE telefone_real = $1 LIMIT 1",
#                 telefone_real,
#             )
#             if row: jid = row["jid"]

#         if not row:
#             print(f">>> [NOVO CLIENTE] Inserindo JID {jid} e Telefone {telefone_real} no banco...")
#             await conexao.execute(
#                 "INSERT INTO conversas_bot (jid, telefone_real, estado_conversa, ultima_interacao) VALUES ($1, $2, 'primeiro_contato', NOW()) ON CONFLICT (jid) DO NOTHING",
#                 jid, telefone_real,
#             )
#             cliente_db = {"estado_conversa": "primeiro_contato"}
#             estado_atual = "primeiro_contato"
#         else:
#             cliente_db = dict(row)
#             estado_atual = cliente_db.get("estado_conversa")
#             is_bot_paused = bool(cliente_db.get("is_bot_paused", False))
#             primeiro_nome = cliente_db.get("primeiro_nome", primeiro_nome)

#         await conexao.execute("UPDATE conversas_bot SET ultima_interacao = NOW() WHERE jid = $1", jid)

#         resultado = None
#         eh_formulario = False
#         formulario_dict = {}

#         if isinstance(entrada_cliente, str):
#             if entrada_cliente == "/retorno_ajuda":
#                 estado_atual = "retorno_pos_ajuda"
#             elif entrada_cliente.startswith("/retorno_frete|||"):
#                 estado_atual = "retorna_bot_pagamento"
#                 cliente_db["payload_chatwoot"] = json.loads(entrada_cliente.split("|||")[1])
#             elif entrada_cliente.startswith("/pedido_finalizado|||"):
#                 estado_atual = "finaliza_pedido"
#                 cliente_db["numero_pedido"] = entrada_cliente.split("|||")[1]
#             elif "flow_token" in entrada_cliente:
#                 try:
#                     formulario_dict = json.loads(entrada_cliente)
#                     eh_formulario = True
#                 except Exception: pass
#         elif isinstance(entrada_cliente, dict) and "flow_token" in entrada_cliente:
#             formulario_dict = entrada_cliente
#             eh_formulario = True

#         if (is_bot_paused or estado_atual == "ajuda_pedido") and estado_atual not in ["retorno_pos_ajuda", "retorna_bot_pagamento", "finaliza_pedido"]:
#             print(f"🤫 [BOT PAUSADO] Cliente {jid} em atendimento humano. Ignorando mensagem.")
#             return

#         if eh_formulario:
#             if estado_atual == "cliente_existe":
#                 formulario_dict["Jid"] = jid
#                 if "screen_0_Escolha_a_opo_1" in formulario_dict or "screen_0_Escolha_a_opo_0" in formulario_dict:
#                     resultado = await processar_cadastro_avaliacao_atendimento(formulario_dict, conexao)
#                 elif "screen_0_D_sua_nota_0" in formulario_dict:
#                     resultado = await processar_cadastro_avaliacao(formulario_dict, conexao)
#                 elif "screen_0_Nome_Nome_Social_0" in formulario_dict:
#                     nome = formulario_dict.get("screen_0_Nome_Nome_Social_0", "").strip()
#                     primeiro = nome.split()[0].upper() if nome else "CLIENTE"
#                     resultado = {"sql_update": f"UPDATE conversas_bot SET nome_cliente = '{nome}', primeiro_nome = '{primeiro}' WHERE jid = '{jid}';"}
#                 elif "screen_0_Endereo_0" in formulario_dict:
#                     endereco = formulario_dict.get("screen_0_Endereo_0", "").strip()
#                     bairro = formulario_dict.get("screen_0_Bairro_1", "").strip()
#                     resultado = {"sql_update": f"UPDATE conversas_bot SET endereco = '{endereco}', bairro = '{bairro}' WHERE jid = '{jid}';"}
#                 else:
#                     resultado = {"sql_update": None}

#                 estado_atual = "ignorar_mensagem"
#                 if isinstance(resultado, dict):
#                     for k in ["payload", "payload_whatsapp", "payload_flow", "mensagens_multiplas"]:
#                         resultado.pop(k, None)
#             else:
#                 if "screen_0_Nome_Nome_Social_0" in formulario_dict: estado_atual = "primeiro_contato"
#                 elif "screen_0_Endereo_0" in formulario_dict: estado_atual = "cadastra_endereco"
#                 elif "screen_0_Escolha_a_opo_1" in formulario_dict or "screen_0_Escolha_a_opo_0" in formulario_dict:
#                     estado_atual = "aguardando_avaliacao_atendimento"
#                     cliente_db["form_data"] = formulario_dict
#                 elif "screen_0_D_sua_nota_0" in formulario_dict:
#                     estado_atual = "aguardando_avaliacao"
#                     cliente_db["form_data"] = formulario_dict

#         notion_headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
#         whatsapp_api_config = {"WHATSAPP_PHONE_NUMBER_ID": WHATSAPP_PHONE_NUMBER_ID, "token": WHATSAPP_ACCESS_TOKEN, "url": WHATSAPP_API_URL}
#         chatwoot_headers = {"api_access_token": os.getenv("CHATWOOT_TOKEN", "")}

#         if estado_atual == "ignorar_mensagem": pass
#         elif not estado_atual or estado_atual in ["primeiro_contato", "inicio"]:
#             if eh_formulario: resultado = processar_cadastro_nome(formulario_dict, jid, telefone_real, conexao, notion_headers, whatsapp_api_config)
#             else: resultado = gerar_mensagem_boas_vindas(jid, telefone_real)
#         elif estado_atual == "cliente_existe":
#             resultado = executar_fluxo_cliente_existe(jid, primeiro_nome)
#         elif estado_atual == "menu_inicio":
#             if str(entrada_cliente) == "3": resultado = await processar_ajuda_pedido(jid, telefone_real, primeiro_nome, cliente_db)
#             else: resultado = processar_menu_inicio(jid, jid, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual == "menu_alternativo":
#             if str(entrada_cliente) == "3":
#                 carrinho_salvo = cliente_db.get("carrinho_json", "[]")
#                 resultado = processar_encerramento_sessao(jid, telefone_real, primeiro_nome, carrinho_salvo, "sair")
#             else: resultado = processar_menu_alternativo(jid, jid, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual == "aguardando_categoria":
#             resultado = processar_aguardando_categoria(jid, telefone_real, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual and estado_atual.startswith("visualizando_cardapio"):
#             resultado = processar_navegacao_cardapio(estado_atual, jid, jid, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual == "aguardando_escolha_item":
#             resultado = processar_escolha_item(jid, jid, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual == "processando_lista_itens":
#             resultado = processar_quantidade_item(jid, jid, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual == "calcula_pedido":
#             resultado = processar_calculo_pedido(jid, jid, primeiro_nome, cliente_db)
#         elif estado_atual in ["visualizando_carrinho", "menu_carrinho"]:
#             resultado = processar_visualizacao_carrinho(jid, jid, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual == "aguardando_alteracao_item":
#             resultado = processar_alteracao_itens(jid, jid, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual == "processando_alteracao_itens":
#             resultado = processando_alteracao_itens(jid, jid, entrada_cliente, cliente_db)
#         elif estado_atual == "existe_cupom":
#             resultado = processar_existe_cupom(jid, jid, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual in ["verifica_cupom", "tenta_cupom"]:
#             resultado = processar_verificacao_cupom(jid, jid, primeiro_nome, entrada_cliente, cliente_db, {})
#         elif estado_atual in ["adiciona_itens_frete", "adiciona_itens_cupom", "adiciona_mais_itens"]:
#             resultado = roteia_adicionar_mais_itens(jid, telefone_real, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual == "adiciona_itens":
#             resultado = processar_adiciona_itens(jid, jid, primeiro_nome, entrada_cliente, cliente_db)
#         elif estado_atual == "cadastra_endereco":
#             resultado = processar_cadastro_endereco(jid, jid, entrada_cliente, cliente_db)
#         elif estado_atual in ["finalizando_pedido", "processa_pedido"]:
#             resultado = processar_pedido(cliente_db, entrada_cliente, conexao, chatwoot_headers)
#         elif estado_atual == "finaliza_pedido":
#             resultado = await processar_finalizacao_pedido({"numero_pedido": cliente_db.get("numero_pedido"), "telefone_real": telefone_real}, conexao)
#         elif estado_atual == "cria_pagamento":
#             resultado = processar_criacao_pagamento(jid, jid, primeiro_nome, cliente_db)
#         elif estado_atual == "pagamento_efetuado":
#             resultado = processar_pagamento_efetuado({"numero_pedido": cliente_db.get("numero_pedido", ""), "telefone_real": jid}, conexao)
#         elif estado_atual == "status_pedido":
#             resultado = processar_status_pagamento({}, cliente_db, conexao, chatwoot_headers)
#         elif estado_atual == "retorna_bot_pagamento":
#             resultado = await processar_retorno_bot_pagamento(cliente_db.get("payload_chatwoot", {}), conexao)
#         elif estado_atual == "aguardando_avaliacao_atendimento":
#             form_data = cliente_db.get("form_data", {})
#             if form_data:
#                 form_data["Jid"] = jid
#                 resultado = await processar_cadastro_avaliacao_atendimento(form_data, conexao)
#             else:
#                 resultado = await processar_cadastro_avaliacao_atendimento({"Jid": jid, "screen_0_Escolha_a_opo_0": "Sim", "screen_0_Escolha_a_opo_1": entrada_cliente}, conexao)
#         elif estado_atual == "aguardando_avaliacao":
#             form_data = cliente_db.get("form_data", {})
#             if form_data:
#                 form_data["Jid"] = jid
#                 resultado = await processar_cadastro_avaliacao(form_data, conexao)
#             else:
#                 resultado = await processar_cadastro_avaliacao({"Jid": jid, "screen_0_D_sua_nota_0": entrada_cliente}, conexao)
#         elif estado_atual == "envia_avaliacao_pedido":
#             resultado = processar_envio_avaliacao(jid, jid, cliente_db)
#         elif estado_atual in ["encerrado", "cliente_sair"]:
#             resultado = processar_encerramento_sessao(jid, telefone_real, primeiro_nome, cliente_db.get("carrinho_json", "[]"), "sair")
#         elif estado_atual == "retorna_menu":
#             resultado = processar_retorno_menu(jid, jid, cliente_db)
#         elif estado_atual in ["ajuda_pedido", "ajuda_e_atendimento"]: pass
#         elif estado_atual == "retorno_pos_ajuda":
#             resultado = await processar_retorno_pos_ajuda(jid, telefone_real, primeiro_nome, cliente_db)
#         else:
#             print(f"Estado '{estado_atual}' não reconhecido para o JID {jid}")
#             return

#         if asyncio.iscoroutine(resultado):
#             resultado = await resultado

#         if isinstance(resultado, dict):
#             sql_cmds = resultado.get("sql_update") or resultado.get("sql_updates") or resultado.get("sql_reseta")
#             if sql_cmds:
#                 if isinstance(sql_cmds, str): sql_cmds = [sql_cmds]
#                 async with conexao.transaction():
#                     for sql in sql_cmds:
#                         if sql and sql.strip(): await conexao.execute(sql)

#             destinatario_final = telefone_real if telefone_real else jid
#             payload_final = resultado.get("payload") or resultado.get("payload_whatsapp") or resultado.get("payload_flow")
#             mensagens_multiplas = resultado.get("mensagens_multiplas", [])

#             if mensagens_multiplas:
#                 for msg in mensagens_multiplas:
#                     payload_base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": destinatario_final}
#                     payload_base.update(msg)
#                     await disparar_whatsapp(payload_base)
#             else:
#                 if not payload_final and "messaging_product" in resultado: payload_final = resultado
#                 if payload_final:
#                     payload_final["to"] = destinatario_final
#                     await disparar_whatsapp(payload_final)

#     except Exception as e:
#         print(f"\n❌ ERRO CRÍTICO NO WORKER (JID: {jid}) ❌")
#         print(f"Detalhes do erro: {e}")
#         traceback.print_exc()
#         print("--------------------------------------------------\n")
#     finally:
#         # A MÁGICA FINAL: Haja o que houver, a conexão volta SEMPRE para a pool!
#         if db_pool:
#             await db_pool.release(conexao)

# # ========================================================
# # ROTINAS AUTOMÁTICAS EM BACKGROUND
# # ========================================================

# async def loop_sessoes_expiradas():
#     while True:
#         try:
#             conexao = await obter_conexao()
#             try:
#                 notion_headers = {"Authorization": f"Bearer {NOTION_TOKEN}"}
#                 chatwoot_headers = {"api_access_token": os.getenv("CHATWOOT_TOKEN", "")}
#                 whatsapp_config = {"url": WHATSAPP_API_URL, "phone_id": WHATSAPP_PHONE_NUMBER_ID, "token": WHATSAPP_ACCESS_TOKEN}

#                 if asyncio.iscoroutinefunction(processar_sessoes_expiradas):
#                     resultado = await processar_sessoes_expiradas(conexao, notion_headers, chatwoot_headers, whatsapp_config)
#                 else:
#                     resultado = processar_sessoes_expiradas(conexao, notion_headers, chatwoot_headers, whatsapp_config)
#                 await executar_resultado_background(resultado, conexao)
#             finally:
#                 if db_pool: await db_pool.release(conexao)
#         except Exception as e: print(f"Erro no loop de sessões expiradas: {e}")
#         await asyncio.sleep(60)

# async def loop_pagamento_expirado():
#     while True:
#         try:
#             conexao = await obter_conexao()
#             try:
#                 notion_headers = {"Authorization": f"Bearer {NOTION_TOKEN}"}
#                 chatwoot_headers = {"api_access_token": os.getenv("CHATWOOT_TOKEN", "")}
#                 whatsapp_config = {"url": WHATSAPP_API_URL, "phone_id": WHATSAPP_PHONE_NUMBER_ID, "token": WHATSAPP_ACCESS_TOKEN}

#                 if asyncio.iscoroutinefunction(processar_pagamentos_expirados):
#                     resultado = await processar_pagamentos_expirados(conexao, notion_headers, chatwoot_headers, whatsapp_config)
#                 else:
#                     resultado = processar_pagamentos_expirados(conexao, notion_headers, chatwoot_headers, whatsapp_config)
#                 await executar_resultado_background(resultado, conexao)
#             finally:
#                 if db_pool: await db_pool.release(conexao)
#         except Exception as e: print(f"Erro no loop de pagamento_expirado: {e}")
#         await asyncio.sleep(60)

# async def loop_cupom_expirado():
#     while True:
#         try:
#             conexao = await obter_conexao()
#             try:
#                 if asyncio.iscoroutinefunction(verificar_e_expirar_cupons): resultado = await verificar_e_expirar_cupons(conexao)
#                 else: resultado = verificar_e_expirar_cupons(conexao)
#                 await executar_resultado_background(resultado, conexao)
#             finally:
#                 if db_pool: await db_pool.release(conexao)
#         except Exception as e: print(f"Erro no loop de cupom_expirado: {e}")
#         await asyncio.sleep(3600)

# async def loop_atualiza_promocoes():
#     while True:
#         try:
#             conexao = await obter_conexao()
#             try:
#                 if asyncio.iscoroutinefunction(processar_atualizacao_promocoes): resultado = await processar_atualizacao_promocoes()
#                 else: resultado = processar_atualizacao_promocoes()
#                 await executar_resultado_background(resultado, conexao)
#             finally:
#                 if db_pool: await db_pool.release(conexao)
#         except Exception as e: print(f"Erro no loop de atualização de promoções: {e}")
#         await asyncio.sleep(43200)

# async def main():
#     print("Iniciando Worker Enterprise com blindagem de Conexão...")
#     asyncio.create_task(loop_sessoes_expiradas())
#     asyncio.create_task(loop_pagamento_expirado())
#     asyncio.create_task(loop_cupom_expirado())
#     asyncio.create_task(loop_atualiza_promocoes())

#     connection = await aio_pika.connect_robust(RABBITMQ_URL)
#     async with connection:
#         channel = await connection.channel()
#         await channel.set_qos(prefetch_count=20)
#         fila_whatsapp = await channel.declare_queue("novos_pedidos", durable=True, arguments={"x-queue-type": "quorum"})
#         await channel.declare_queue("pagamento_efetuado", durable=True, arguments={"x-queue-type": "quorum"})
#         await channel.declare_queue("cria_pagamento", durable=True, arguments={"x-queue-type": "quorum"})
#         await channel.declare_queue("finaliza_pedido", durable=True, arguments={"x-queue-type": "quorum"})
#         await channel.declare_queue("status_pedido", durable=True, arguments={"x-queue-type": "quorum"})
#         await channel.declare_queue("retorna_bot", durable=True, arguments={"x-queue-type": "quorum"})

#         print("Worker a escutar todas as filas com sucesso!")
#         async with fila_whatsapp.iterator() as queue_iter:
#             async for message in queue_iter:
#                 async with message.process():
#                     try:
#                         dados = json.loads(message.body.decode())
#                         print(f">>> [RABBITMQ] Mensagem nova recebida na fila! Dados: {dados}")
#                         jid = dados.get("jid")
#                         telefone_real = dados.get("telefone_real", jid)
#                         primeiro_nome = dados.get("primeiro_nome", "Cliente")
#                         entrada_cliente = dados.get("entrada_cliente", "")
#                         await processar_maquina_estados(jid, telefone_real, primeiro_nome, entrada_cliente)
#                     except Exception as e:
#                         print(f"Erro ao processar mensagem na fila 'novos_pedidos': {e}")

# if __name__ == "__main__":
#     asyncio.run(main())
