# ============================================================================
# FUNCOES_JANELA_ARMADURA_LONGITUDINAL.PY  –  v4.0
# ============================================================================
#
# Módulo de funções auxiliares para a janela de dimensionamento de armadura
# longitudinal.
#
# HISTÓRICO DE VERSÕES
# v3.0 – Refatoração completa (desenho DCL, hover interativo, etc.)
# v4.0 – [FIX-1]  Corrigida função gerar_html_resumo_primeira_iteracao:
#          agora recebe o objeto ResultadoDimensionamento completo ao invés
#          de (As_calc, x, d), expondo corretamente os estados de
#          secao_insuficiente e armadura_dupla_necessaria.
#        [CLEANUP-1] Removidas as funções de desenho do DCL (desenhar_dcl,
#          _obter_segmentos_viga, desenhar_dcl_secoes) que não são mais
#          utilizadas pela janela. O envelope de momento foi migrado para
#          logica_janela_armadura_longitudinal via desenhar_envelope_calculo.
#        [CLEANUP-2] Removidas importações não utilizadas após a limpeza acima
#          (matplotlib, patches, numpy, Callable, Union, List).
# ============================================================================

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional, Dict, Any, Tuple

if TYPE_CHECKING:
    from modules.Calculadora_Flexao_Fadiga import CalculadoraFlexaoFadiga
    from modules.dimensionamento_flexao import ResultadoDimensionamento


# ==============================================================================
# UTILITÁRIO GERAL DE MAPEAMENTO DE TIPOS
# ==============================================================================

def _mapear_tipo_interno(tipo_ui: str) -> str:
    """Converte o texto da UI para o identificador interno usado no cálculo."""
    mapeamento = {
        "Isostática: Múltiplos Vãos Biapoioados":       "biapoiada",
        "Isostática: Biapoiada com Balanço":             "isostatica_em_balanco",
        "Hiperestática: Vão Contínuo sem Balanço":       "hiperestatica_sem_balanco",
        "Hiperestática: Vão Contínuo com Balanço":       "hiperestatica_com_balanco",
    }
    return mapeamento.get(tipo_ui, "biapoiada")


# ==============================================================================
# 1. FUNÇÕES GERADORAS DE HTML
# ==============================================================================

def gerar_html_d_estimado(h_cm):
    """Gera o HTML com a estimativa de altura útil d a partir da altura total h."""
    d_inf = 0.85 * h_cm
    d_sup = 0.90 * h_cm
    html = f"""
    <div style="font-family: sans-serif; color: #e0e0e0; text-align: center;">
        <div style="font-size: 11pt;">
            <b>Altura útil da seção estimada (d):</b>
            Altura da Seção (h) = {h_cm:.2f} cm &rarr;
            <span style="color: #81c784;">d<sub>inf</sub> = 0,85 &middot; h = {d_inf:.2f} cm</span> |
            <span style="color: #81c784;">d<sub>sup</sub> = 0,90 &middot; h = {d_sup:.2f} cm</span>
        </div>
        <div style="font-size: 9pt; color: #bbb; margin-top: 8px; font-style: italic;">
            Obs: Os valores de 0,85 &middot; h e 0,90 &middot; h são práticas de pré-dimensionamento de longarinas
            devido à alta taxa de armadura. Estes valores são utilizados na iteração inicial do cálculo,
            devendo ser confrontados posteriormente com o d real advindo do A<sub>s</sub> adotado.
        </div>
    </div>
    """
    return d_inf, d_sup, html


def gerar_html_resumo_primeira_iteracao(resultado: "ResultadoDimensionamento") -> str:
    """
    Gera o resumo HTML do dimensionamento à flexão simples.

    [v4.0] Refatorado: recebe o objeto ResultadoDimensionamento completo para
    poder exibir feedback realista em todos os três casos possíveis:

    CASO 1 – secao_insuficiente == True
        O momento solicitante excede a capacidade máxima da seção (kx > 1,0 ou
        Msd > Mrd_max). Exibe cartão vermelho com ações recomendadas e NÃO
        exibe As_calc (valor inválido neste estado).

    CASO 2 – armadura_dupla_necessaria == True
        kx_lim < kx ≤ 1,0: a seção é suficiente, mas exige armadura de
        compressão (A's). Exibe cartão laranja com As, A's, Mrd_lim e ΔM.

    CASO 3 – Dimensionamento normal (OK)
        Exibe domínio de deformação (1–3) baseado em kx vs kx_lim.

    Parâmetros
    ----------
    resultado : ResultadoDimensionamento
        Objeto retornado por CalculadoraFlexaoSimples.dimensionar().
    """
    # ── CASO 1: Seção Insuficiente ─────────────────────────────────────────────
    if resultado.secao_insuficiente:
        msd_abs = abs(resultado.Msd)
        html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #fca5a5;
                    padding: 18px; border-radius: 8px;
                    background-color: #2d1515;
                    border-left: 5px solid #f87171;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.4);">
            <div style="font-size: 14pt; font-weight: bold; color: #f87171;
                        text-transform: uppercase; letter-spacing: 0.5px;
                        margin-bottom: 10px;">
                &#10060; SEÇÃO INSUFICIENTE
            </div>
            <p style="font-size: 11pt; color: #e0e0e0; margin: 0 0 8px 0;">
                O momento solicitante
                <b style="color: #f87171;">M<sub>sd</sub> = {msd_abs:.2f} kN&middot;m</b>
                excede a capacidade resistente máxima da seção.
            </p>
            <p style="font-size: 10pt; color: #c0c0c0; margin: 0 0 14px 0;">
                Mesmo utilizando toda a altura útil disponível, a seção de concreto
                não consegue equilibrar o esforço solicitante. O índice de posição
                relativa da linha neutra ultrapassa k<sub>x</sub> = 1,0.
            </p>
            <hr style="border: 0; border-top: 1px solid #5a2222; margin: 10px 0;">
            <b style="font-size: 11pt; color: #fca5a5;">&#9888; Ações Recomendadas:</b>
            <ul style="font-size: 10pt; color: #c0c0c0; margin-top: 8px;
                       line-height: 1.8; padding-left: 20px;">
                <li>Aumentar a <b>altura total da viga (h)</b>;</li>
                <li>Aumentar a <b>largura da alma (b<sub>w</sub>)</b>;</li>
                <li>Aumentar a <b>resistência do concreto (f<sub>ck</sub>)</b>;</li>
                <li>Considerar a utilização de <b>protensão</b>.</li>
            </ul>
            <p style="font-size: 9pt; color: #a87070; margin-top: 10px; font-style: italic;">
                Não é possível calcular uma área de aço válida para esta configuração.
            </p>
        </div>
        """
        return html

    # ── CASO 2: Armadura Dupla Necessária ─────────────────────────────────────
    if resultado.armadura_dupla_necessaria:
        msd_abs   = abs(resultado.Msd)
        mrd_lim   = resultado.Mrd_lim   if resultado.Mrd_lim   is not None else 0.0
        delta_m   = resultado.delta_M   if resultado.delta_M   is not None else 0.0
        as_linha  = resultado.As_linha  if resultado.As_linha  is not None else 0.0

        html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0;
                    padding: 18px; border-radius: 8px;
                    background-color: #2d2010;
                    border-left: 5px solid #f59e0b;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.4);">
            <div style="font-size: 14pt; font-weight: bold; color: #fbbf24;
                        text-transform: uppercase; letter-spacing: 0.5px;
                        margin-bottom: 12px;">
                &#9888; ARMADURA DUPLA NECESSÁRIA
            </div>
            <p style="font-size: 10pt; color: #c0c0c0; margin: 0 0 14px 0;">
                O momento solicitante excede o limite de ductilidade simples
                (k<sub>x</sub> &gt; k<sub>x,lim</sub> = <b>{resultado.kx_lim:.2f}</b>),
                exigindo armadura de compressão (A'<sub>s</sub>).
            </p>
            <hr style="border: 0; border-top: 1px solid #5a3a10; margin: 10px 0;">

            <table style="width:100%; border-collapse:collapse; font-size:11pt;
                          color:#e0e0e0; margin-bottom:10px;">
                <tr>
                    <td style="padding:5px 0; color:#b0b0b0;">M<sub>sd</sub> solicitante:</td>
                    <td style="padding:5px 0; font-weight:bold;
                               color:#fbbf24;">{msd_abs:.2f} kN&middot;m</td>
                </tr>
                <tr>
                    <td style="padding:5px 0; color:#b0b0b0;">M<sub>rd,lim</sub> (limite simples):</td>
                    <td style="padding:5px 0; font-weight:bold;
                               color:#90caf9;">{mrd_lim:.2f} kN&middot;m</td>
                </tr>
                <tr>
                    <td style="padding:5px 0; color:#b0b0b0;">&Delta;M (excedente):</td>
                    <td style="padding:5px 0; font-weight:bold;
                               color:#fbbf24;">{delta_m:.2f} kN&middot;m</td>
                </tr>
            </table>

            <div style="display:flex; gap:12px; margin-top:6px;">
                <div style="flex:1; background-color:#1e1e1e; padding:12px;
                            border-radius:6px; text-align:center;
                            border-top: 3px solid #4ade80;">
                    <div style="font-size:9pt; color:#a0a0a0; margin-bottom:4px;">
                        A<sub>s</sub> (tração)</div>
                    <div style="font-size:14pt; font-weight:bold; color:#4ade80;">
                        {resultado.As_adotar:.2f} cm²</div>
                </div>
                <div style="flex:1; background-color:#1e1e1e; padding:12px;
                            border-radius:6px; text-align:center;
                            border-top: 3px solid #fbbf24;">
                    <div style="font-size:9pt; color:#a0a0a0; margin-bottom:4px;">
                        A'<sub>s</sub> (compressão)</div>
                    <div style="font-size:14pt; font-weight:bold; color:#fbbf24;">
                        {as_linha:.2f} cm²</div>
                </div>
            </div>

            <p style="font-size:9pt; color:#a07040; margin-top:12px; font-style:italic;">
                Verifique o posicionamento da armadura de compressão no detalhamento.
                Confirme o d' (cobrimento da A'<sub>s</sub>) para validar a hipótese de escoamento.
            </p>
        </div>
        """
        return html

    # ── CASO 3: Dimensionamento Normal ────────────────────────────────────────
    kx      = resultado.kx
    kx_lim  = resultado.kx_lim

    # Classificação por domínio de deformação (NBR 6118)
    if kx <= 0:
        dominio_str   = "DOMÍNIO 1"
        cor_status    = "#fbbf24"
        comportamento = "Tração Não Uniforme — Seção Totalmente Tracionada"
        cor_fundo     = "#2a2510"
        cor_borda     = "#fbbf24"
    elif kx <= 0.259:
        dominio_str   = "DOMÍNIO 2"
        cor_status    = "#fbbf24"
        comportamento = "Flexão Simples — Ruína por Deformação do Aço (Dúctil)"
        cor_fundo     = "#2a2510"
        cor_borda     = "#fbbf24"
    elif kx <= kx_lim:
        dominio_str   = "DOMÍNIO 3"
        cor_status    = "#4ade80"
        comportamento = "Flexão Simples — Ótimo Aproveitamento (Dúctil)"
        cor_fundo     = "#102a18"
        cor_borda     = "#4ade80"
    else:
        # kx > kx_lim mas armadura_dupla_necessaria=False: raro, mas tratado
        dominio_str   = f"DOMÍNIO 3 — ATENÇÃO (k<sub>x</sub> &gt; k<sub>x,lim</sub>)"
        cor_status    = "#f87171"
        comportamento = f"k<sub>x</sub> excedeu o limite de ductilidade ({kx_lim:.2f}). Verificar."
        cor_fundo     = "#2d1515"
        cor_borda     = "#f87171"

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0; padding: 15px;
                border-radius: 8px; background-color: #1e1e1e; text-align: center;
                border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">

        <div style="margin-bottom: 12px;">
            <span style="font-size: 10pt; color: #bbbbbb;">
                Área de Aço Calculada (A<sub>s,calc</sub>):
            </span><br>
            <b style="font-size: 14pt; color: #90caf9;">
                {resultado.As_adotar:.2f} cm²
            </b>
            <span style="font-size: 9pt; color: #888; margin-left: 6px;">
                (min.: {resultado.As_min:.2f} cm²)
            </span>
        </div>

        <div style="margin-bottom: 12px;">
            <span style="font-size: 10pt; color: #bbbbbb;">
                Linha Neutra (x):
                <b style="color: #e0e0e0;">{resultado.x:.2f} cm</b>
            </span><br>
            <span style="font-size: 10pt; margin-top: 5px; display: block; color: #bbbbbb;">
                Linha Neutra Relativa k<sub>x</sub> = x/d:
                <b style="font-size: 13pt; color: {cor_status};">{kx:.4f}</b>
                <span style="font-size: 9pt; color: #888;">
                    / lim. {kx_lim:.2f}
                </span>
            </span>
        </div>

        <hr style="border: 0; border-top: 1px solid #333; margin: 12px 0;">

        <div style="font-size: 12pt; font-weight: bold; color: {cor_status};
                    background-color: {cor_fundo}; padding: 8px 12px;
                    border-radius: 6px; border-left: 4px solid {cor_borda};
                    text-align: left; margin-bottom: 6px;">
            {dominio_str}
        </div>
        <div style="font-size: 9pt; color: #a0a0a0; margin-top: 4px; font-style: italic;">
            {comportamento}
        </div>

        <div style="font-size: 9pt; color: #e0e0e0; background-color: #252525;
                    padding: 10px 12px; border-radius: 4px; margin-top: 12px;
                    border-left: 5px solid {cor_status}; text-align: left;
                    line-height: 1.5;">
            <b style="color: {cor_status}; font-size: 9pt;">NOTA NORMATIVA (NBR 6118):</b><br>
            Para assegurar a <b>ductilidade</b>, a <b>Linha Neutra Relativa</b>
            deve satisfazer k<sub>x</sub> &le; k<sub>x,lim</sub> =
            <b>{kx_lim:.2f}</b>. Valores superiores exigem
            redimensionamento ou armadura de compressão (A'<sub>s</sub>).
        </div>
    </div>
    """
    return html


def gerar_html_d_real(d_real_cm):
    """Gera o resumo HTML para o d_real determinado a partir do baricentro da armadura."""
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0; text-align: center;
                padding: 14px; border-radius: 8px; background-color: #1e1e1e;
                border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <div style="font-size: 11pt; font-weight: bold; margin-bottom: 8px;">
            d<sub>real_calculado</sub>: <span style="color: #4ade80;">{d_real_cm:.1f} cm</span>
        </div>
        <div style="font-size: 9pt; color: #b0b0b0; line-height: 1.3;">
            Valor obtido através da determinação do <b>centro de gravidade</b>
            do grupo de barras, conforme o arranjo no desenho abaixo.
        </div>
    </div>
    """
    return html


def gerar_html_as_adotado(as_total, n_barras, phi_mm):
    """Gera o resumo HTML para a armadura adotada (Aₛ,adotado)."""
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0; text-align: center;
                padding: 14px; border-radius: 8px; background-color: #1e1e1e;
                border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <div style="font-size: 11pt; font-weight: bold; margin-bottom: 8px;">
            A<sub>s,adotado</sub>: <span style="color: #90caf9;">{as_total:.2f} cm²</span>
        </div>
        <div style="font-size: 10pt; color: #e0e0e0; background-color: #252525;
                    padding: 6px 12px; border-radius: 4px;
                    display: inline-block; margin-top: 5px;">
            <b>{n_barras} &times; &oslash;{phi_mm}</b>
        </div>
        <div style="font-size: 8.5pt; color: #a0a0a0; margin-top: 10px; font-style: italic;">
            Arranjo de armadura longitudinal calculado para a seção transversal.
        </div>
    </div>
    """
    return html


def gerar_html_comparacao(as_sup_calc, as_sup_adot, as_inf_calc, as_inf_adot,
                           d_sup_calc, d_sup_adot, d_inf_calc, d_inf_adot):
    """
    Gera um memorial de cálculo profissional em HTML com layout de duas colunas.
    Compara armaduras Inferiores (Positivas) e Superiores (Negativas).
    """

    def calcular_metricas(as_calc, as_adot, d_calc, d_adot):
        if (as_calc is None or as_adot is None) and (d_calc is None or d_adot is None):
            return None

        if as_calc is not None and as_adot is not None:
            sucesso_as = (as_adot >= as_calc - 0.001)
            cor_as     = "#4ade80" if sucesso_as else "#f87171"
            txt_as     = (
                "Armadura adotada suficiente (As,adot &ge; As,calc)."
                if sucesso_as else
                "Armadura adotada insuficiente (As,adot &lt; As,calc)."
            )
        else:
            cor_as = "#888"
            txt_as = "Verificação não realizada."

        if d_calc is not None and d_adot is not None and d_calc > 0:
            erro_d = abs(d_adot - d_calc) / d_calc * 100
            if erro_d <= 3.0:
                cor_d    = "#4ade80"
                status_d = "Convergência excelente."
            elif erro_d <= 7.0:
                cor_d    = "#fbbf24"
                status_d = "Diferença moderada, recomenda-se avaliação."
            else:
                cor_d    = "#f87171"
                status_d = "Diferença elevada, recomenda-se nova iteração."
            erro_d_txt = f"{erro_d:.1f}%"
        else:
            cor_d      = "#888"
            status_d   = "Verificação não realizada."
            erro_d_txt = "-"

        return {
            "as_calc": f"{as_calc:.2f}" if as_calc is not None else "-",
            "as_adot": f"{as_adot:.2f}" if as_adot is not None else "-",
            "cor_as":  cor_as,
            "txt_as":  txt_as,
            "d_calc":  f"{d_calc:.2f}" if d_calc is not None else "-",
            "d_adot":  f"{d_adot:.2f}" if d_adot is not None else "-",
            "cor_d":   cor_d,
            "status_d": status_d,
            "erro_d":  erro_d_txt,
        }

    inf = calcular_metricas(as_inf_calc, as_inf_adot, d_inf_calc, d_inf_adot)
    sup = calcular_metricas(as_sup_calc, as_sup_adot, d_sup_calc, d_sup_adot)

    def render_coluna(dados, titulo):
        if not dados:
            return f"""
            <td style='width: 50%; vertical-align: top; padding: 15px; color: #a0a0a0;
                       font-style: italic; background-color: #1e1e1e;'>
                <div style="font-size: 13pt; font-weight: bold; color: #90caf9;
                            margin-bottom: 10px;">{titulo}</div>
                Não há armadura dimensionada para esta região.
            </td>"""

        if "insuficiente" in dados['txt_as'].lower():
            badge = ('<span style="font-size: 12pt; font-weight: 700; color: #f87171; '
                     'background-color: #7f1d1d; padding: 2px 8px; border-radius: 4px;">'
                     '&#10007; REPROVADO</span>')
        elif "suficiente" in dados['txt_as'].lower():
            badge = ('<span style="font-size: 12pt; font-weight: 700; color: #4ade80; '
                     'background-color: #166534; padding: 2px 8px; border-radius: 4px;">'
                     '&#10003; APROVADO</span>')
        else:
            badge = ""

        return f"""
        <td style="width: 50%; vertical-align: top; padding: 16px;
                   background-color: #1e1e1e; border: none;">
            <div style="background-color: #252525; padding: 8px 12px; margin-bottom: 16px;
                        border-radius: 4px; display: flex; align-items: center;
                        justify-content: space-between;">
                <span style="font-size: 13pt; font-weight: 700; color: #90caf9;">{titulo}</span>
                {badge}
            </div>
            <div style="margin-bottom: 20px;">
                <div style="font-size: 11pt; color: #bbbbbb; margin-bottom: 8px;
                            border-bottom: 1px solid #333; padding-bottom: 4px;">
                    Verificação da Área de Armadura Longitudinal
                </div>
                <table border="0" style="margin: 0; border-collapse: collapse; width: 100%;"
                       cellspacing="2" cellpadding="0">
                    <tr>
                        <td style="padding: 4px 0; color: #c0c0c0; font-size: 12pt;">
                            Área calculada:</td>
                        <td style="padding: 4px 0; font-weight: 700; color: #90caf9;
                                   font-size: 12pt;">{dados['as_calc']} cm²</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #c0c0c0; font-size: 12pt;">
                            Área adotada:</td>
                        <td style="padding: 4px 0; font-weight: 700; color: #90caf9;
                                   font-size: 12pt;">{dados['as_adot']} cm²</td>
                    </tr>
                </table>
                <div style="margin-top: 8px; font-size: 10pt; color: {dados['cor_as']};
                            line-height: 1.4;">{dados['txt_as']}</div>
            </div>
            <div>
                <div style="font-size: 11pt; color: #bbbbbb; margin-bottom: 8px;
                            border-bottom: 1px solid #333; padding-bottom: 4px;">
                    Verificação da Altura Útil da Seção
                </div>
                <table border="0" style="margin: 0; border-collapse: collapse; width: 100%;"
                       cellspacing="2" cellpadding="0">
                    <tr>
                        <td style="padding: 4px 0; color: #c0c0c0; font-size: 12pt;">
                            Altura útil calculada:</td>
                        <td style="padding: 4px 0; font-weight: 700; color: #90caf9;
                                   font-size: 12pt;">{dados['d_calc']} cm</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #c0c0c0; font-size: 12pt;">
                            Altura útil adotada:</td>
                        <td style="padding: 4px 0; font-weight: 700; color: #90caf9;
                                   font-size: 12pt;">{dados['d_adot']} cm</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #c0c0c0; font-size: 12pt;">
                            Diferença relativa:</td>
                        <td style="padding: 4px 0; font-weight: 700; color: #90caf9;
                                   font-size: 12pt;">{dados['erro_d']}</td>
                    </tr>
                </table>
                <div style="margin-top: 8px; font-size: 10pt; color: {dados['cor_d']};
                            line-height: 1.4;">{dados['status_d']}</div>
            </div>
        </td>"""

    col_inf = render_coluna(inf, "&#11015; Armadura Inferior (A<sub>s</sub>)")
    col_sup = render_coluna(sup, "&#11014; Armadura Superior (A'<sub>s</sub>)")

    html_final = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0; padding: 20px;
                background-color: #121212; border-radius: 12px;
                max-width: 1000px; margin: 0 auto;">
        <div style="text-align: center; margin-bottom: 25px; background-color: #1e1e1e;
                    padding: 16px; border-radius: 8px;">
            <h2 style="margin: 0; font-size: 18pt; font-weight: 700; color: #ffffff;
                       letter-spacing: 1px;">
                Memorial de Verificação de Dimensionamento
            </h2>
            <div style="font-size: 10pt; color: #a0a0a0; margin-top: 6px;">
                Comparação entre valores calculados e valores adotados no detalhamento
            </div>
        </div>
        <table style="width: 100%; border-collapse: collapse; table-layout: fixed;
                      margin: 0 auto; text-align: left;">
            <tr>{col_inf}{col_sup}</tr>
        </table>
        <div style="margin-top: 24px; padding: 14px 16px; background-color: #1e1e1e;
                    border-radius: 6px; border-left: 5px solid #90caf9;">
            <span style="font-size: 10pt; color: #b0b0b0; line-height: 1.5;">
                <b style="color: #e0e0e0;">Critério técnico adotado:</b>
                A área de armadura adotada deve ser &ge; à área calculada.
                A altura útil influencia o braço de alavanca interno. Diferenças
                significativas indicam necessidade de reavaliação do dimensionamento,
                recomendando-se nova iteração de cálculo.
            </span>
        </div>
    </div>
    """
    return html_final


# ==============================================================================
# 2. RELAÇÃO MODULAR
# ==============================================================================

def calcular_relacao_modular(classe_concreto: str, tipo_agregado: str,
                              ativo: bool = True):
    """
    Calcula η = Es / Eci conforme NBR 6118:2023 § 8.2.8.

    Retorna (eta, html_memorial).
    """
    fck = int(classe_concreto.replace('C', ''))
    agregados = {
        "basalto": 1.2, "diabásio": 1.2,
        "granito": 1.0, "gnaisse": 1.0,
        "calcário": 0.9, "arenito": 0.7,
    }
    alfa_e = 1.0
    for nome, valor in agregados.items():
        if nome in tipo_agregado.lower():
            alfa_e = valor
            break

    eci = alfa_e * 5600 * math.sqrt(fck)
    es  = 210_000
    eta = es / eci
    html = _gerar_html_relacao_modular(fck, tipo_agregado, alfa_e, eci, es, eta, ativo)
    return eta, html


def _gerar_html_relacao_modular(fck, agregado, alfa_e, eci, es, eta, ativo):
    """Gera o HTML do memorial de cálculo da relação modular."""
    c_prim  = "#90caf9" if ativo else "#888888"
    c_suc   = "#4ade80" if ativo else "#888888"
    c_aler  = "#fbbf24" if ativo else "#888888"
    c_borda = "#333333" if ativo else "#555555"
    c_txt   = "#e0e0e0" if ativo else "#aaaaaa"
    fundo_b = "#252525" if ativo else "#2a2a2a"

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; font-size: 13pt; color: {c_txt};
                line-height: 1.6; background-color: #1e1e1e; padding: 20px;
                border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <div style="border-left: 5px solid {c_prim}; padding-left: 15px; margin-bottom: 20px;">
            <b style="font-size: 15pt; text-transform: uppercase; color: #ffffff;">
                Memorial de Cálculo: Relação Modular</b><br>
            <span style="font-size: 10pt; color: #a0a0a0;">
                Referência: ABNT NBR 6118:2023 § 8.2.8 | Aço CA&#8209;50
                (E<sub>s</sub> = 210 GPa)</span>
        </div>
        <div style="background: rgba(255,255,255,0.03); padding: 15px; border-radius: 8px;
                    text-align: center; margin-bottom: 20px; border: 1px dashed {c_borda};">
            <div style="font-style: italic; font-size: 13pt; margin-bottom: 8px; color: {c_txt};">
                1) E<sub>ci</sub> = &alpha;<sub>E</sub> &middot; 5600 &middot; &radic;f<sub>ck</sub>
            </div>
            <div style="font-style: italic; font-size: 13pt; margin-bottom: 8px; color: {c_txt};">
                2) E<sub>s</sub> = 210&nbsp;000 MPa &emsp;(Aço CA&#8209;50)
            </div>
            <div style="font-style: italic; font-size: 13pt; color: {c_txt};">
                3) &eta; = E<sub>s</sub> / E<sub>ci</sub>
            </div>
        </div>
        <div style="margin-bottom: 20px;">
            <b style="color: {c_prim};">Cálculo com Valores:</b>
            <div style="background: {fundo_b}; padding: 15px; border-radius: 8px;
                        border: 1px solid {c_borda};">
                <div style="font-style: italic; font-size: 12pt; margin-bottom: 10px; color: {c_txt};">
                    1) E<sub>ci</sub> = {alfa_e:.1f} &middot; 5600 &middot; &radic;{fck} =
                    <b style="color:{c_suc};">{eci:.2f} MPa</b>
                </div>
                <div style="font-style: italic; font-size: 12pt; margin-bottom: 10px; color: {c_txt};">
                    2) E<sub>s</sub> = 210&nbsp;000 MPa (fixo para CA&#8209;50)
                </div>
                <div style="font-style: italic; font-size: 12pt; color: {c_txt};">
                    3) &eta; = {es} / {eci:.2f} =
                    <b style="color:{c_aler};">{eta:.3f}</b>
                </div>
            </div>
        </div>
        <div style="text-align: center; padding-top: 15px; border-top: 1px solid {c_borda};">
            <span style="font-size: 14pt; color: {c_txt};">Relação Modular Final (<b>&eta;</b>): </span>
            <span style="font-size: 18pt; color: {c_suc}; font-weight: bold;">{eta:.2f}</span>
            <span style="font-size: 11pt; color: #a0a0a0; display: block; margin-top: 5px;">
                (adimensional)</span>
        </div>
    </div>
    """
    return html


# ==============================================================================
# 3. AMPLITUDE DE TENSÃO
# ==============================================================================

def calcular_amplitude_tensao(bitola_superior=None, bitola_inferior=None,
                               ativo: bool = True):
    """
    Calcula as amplitudes de tensão admissíveis Δf_fad conforme Tabela 23.2
    da NBR 6118:2023.

    Retorna (delta_sup, delta_inf, html_memorial).
    """
    tabela = {
        10.0: 190, 12.5: 190, 16.0: 190, 20.0: 185,
        22.0: 180, 25.0: 175, 32.0: 165, 40.0: 150,
    }

    def obter_delta(diam):
        if diam is None:
            return None
        if diam in tabela:
            return tabela[diam]
        diams_ord = sorted(tabela.keys())
        if diam < diams_ord[0]:
            x1, x2 = diams_ord[0], diams_ord[1]
        elif diam > diams_ord[-1]:
            x1, x2 = diams_ord[-2], diams_ord[-1]
        else:
            x1, x2 = next(
                (diams_ord[i], diams_ord[i+1])
                for i in range(len(diams_ord)-1)
                if diams_ord[i] <= diam <= diams_ord[i+1]
            )
        y1, y2 = tabela[x1], tabela[x2]
        return y1 + (diam - x1) * (y2 - y1) / (x2 - x1)

    delta_sup = obter_delta(bitola_superior)
    delta_inf = obter_delta(bitola_inferior)
    html = _gerar_html_amplitude_tensao(
        bitola_superior, delta_sup, bitola_inferior, delta_inf, tabela, ativo
    )
    return delta_sup, delta_inf, html


def _gerar_html_amplitude_tensao(bitola_sup, delta_sup, bitola_inf, delta_inf,
                                  tabela, ativo):
    """Gera o HTML do memorial de cálculo da amplitude de tensão admissível."""
    c_prim  = "#90caf9" if ativo else "#888888"
    c_suc   = "#4ade80" if ativo else "#888888"
    c_borda = "#333333" if ativo else "#555555"
    c_txt   = "#e0e0e0" if ativo else "#aaaaaa"
    fundo_b = "#252525" if ativo else "#2a2a2a"
    c_tit   = "#ffffff" if ativo else "#cccccc"

    tabela_html = "".join(
        f"<tr><td style='padding:4px 10px; color:{c_txt};'>{d:g}</td>"
        f"<td style='padding:4px 10px; text-align:right; color:{c_txt};'>{v}</td></tr>"
        for d, v in sorted(tabela.items())
    )
    sup_str       = f"{bitola_sup:g} mm"  if bitola_sup  is not None else "—"
    inf_str       = f"{bitola_inf:g} mm"  if bitola_inf  is not None else "—"
    delta_sup_str = f"{delta_sup:.1f} MPa" if delta_sup is not None else "—"
    delta_inf_str = f"{delta_inf:.1f} MPa" if delta_inf is not None else "—"

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; font-size: 13pt; color: {c_txt};
                line-height: 1.6; background-color: #1e1e1e; padding: 20px;
                border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <div style="border-left: 5px solid {c_prim}; padding-left: 15px; margin-bottom: 20px;">
            <b style="font-size: 15pt; text-transform: uppercase; color: {c_tit};">
                Memorial: Amplitude de Tensão Admissível (&Delta;f<sub>fad,sd</sub>)</b><br>
            <span style="font-size: 10pt; color: #a0a0a0;">
                Referência: ABNT NBR 6118:2023 – Tabela 23.2</span>
        </div>
        <div style="margin-bottom: 25px;">
            <b style="color: {c_prim};">Valores Tabelados (MPa):</b>
            <table style="border-collapse: collapse; margin-top: 8px; width: auto;
                          background: rgba(0,0,0,0.1); border: 1px solid {c_borda};">
                <tr style="background: rgba(255,255,255,0.05);">
                    <th style="padding:6px 12px; border-bottom: 1px solid {c_borda};
                               color:{c_txt};">Diâmetro &phi; (mm)</th>
                    <th style="padding:6px 12px; border-bottom: 1px solid {c_borda};
                               color:{c_txt};">&Delta;f<sub>fad</sub> (MPa)</th>
                </tr>
                {tabela_html}
            </table>
        </div>
        <div style="margin-bottom: 20px;">
            <b style="color: {c_prim};">Armaduras Analisadas:</b>
            <div style="background: {fundo_b}; padding: 15px; border-radius: 8px;
                        border: 1px solid {c_borda}; margin-top: 10px;">
                <div style="font-style: italic; font-size: 12pt;
                            margin-bottom: 12px; color: {c_txt};">
                    &bull; <b>Armadura Superior:</b> &phi; = {sup_str}
                    <span style="margin-left: 20px;">
                        &rarr; &Delta;f<sub>fad,sup</sub> =
                        <b style="color:{c_suc};">{delta_sup_str}</b></span>
                </div>
                <div style="font-style: italic; font-size: 12pt; color: {c_txt};">
                    &bull; <b>Armadura Inferior:</b> &phi; = {inf_str}
                    <span style="margin-left: 20px;">
                        &rarr; &Delta;f<sub>fad,inf</sub> =
                        <b style="color:{c_suc};">{delta_inf_str}</b></span>
                </div>
            </div>
        </div>
    </div>
    """
    return html


# ==============================================================================
# 4. HTML VERIFICAÇÃO DE FADIGA
# ==============================================================================

def obter_html_verificacao_fadiga(calculadora: "CalculadoraFlexaoFadiga") -> str:
    """
    Gera o HTML de resumo da verificação de fadiga executada pela calculadora.

    Args
    ----
    calculadora : CalculadoraFlexaoFadiga
        Instância que já executou verificar_fadiga().

    Returns
    -------
    str: HTML formatado.
    """
    resultado = calculadora.ultimo_resultado
    motor     = calculadora.ultimo_motor

    if resultado is None or motor is None:
        raise ValueError(
            "Nenhuma verificação de fadiga realizada. "
            "Execute calculadora.verificar_fadiga() antes."
        )

    r = resultado
    m = motor

    def badge(ok: bool) -> str:
        if ok:
            return ('<span style="background:#166534; color:#4ade80; '
                    'padding:3px 10px; border-radius:14px; font-weight:bold; '
                    'font-size:12pt; border:1px solid #16a34a;">&#10003; APROVADO</span>')
        return ('<span style="background:#7f1d1d; color:#f87171; '
                'padding:3px 10px; border-radius:14px; font-weight:bold; '
                'font-size:12pt; border:1px solid #dc2626;">&#10007; REPROVADO</span>')

    bloco_inf = ""
    if m.As_inf > 0:
        as_corr_str = (f"{r.as_inf_corrigida:.2f} cm²"
                       if isinstance(r.as_inf_corrigida, float)
                       else r.as_inf_corrigida)
        bloco_inf = f"""
        <div style="margin-top: 18px; padding: 12px; background-color: #252525;
                    border-radius: 5px; text-align: center;">
            <div style="display: flex; justify-content: space-between;
                        align-items: center; margin-bottom: 8px;">
                <span style="font-size: 14pt; font-weight: bold; color: #90caf9;">
                    &#11015; Armadura Inferior (A<sub>s</sub>)</span>
                {badge(r.verifica_inf)}
            </div>
            <table style="width: 100%; font-size: 12pt; color: #e0e0e0;
                          border-collapse: collapse; text-align: center;">
                <tr><td>&Delta;&sigma; :</td><td><strong>{r.delta_sigma_inf_MPa:.2f} MPa</strong></td></tr>
                <tr><td>&Delta;f<sub>fad,sd</sub> :</td>
                    <td><strong>{r.delta_f_fad_sd_inf:.2f} MPa</strong></td></tr>
                <tr><td>k<sub>fad</sub> :</td>
                    <td><strong>{r.k_fad_inf:.4f}</strong></td></tr>
                <tr><td>A<sub>s</sub> corrigida :</td>
                    <td><strong style="color: #90caf9;">{as_corr_str}</strong></td></tr>
            </table>
        </div>"""

    bloco_sup = ""
    if m.As_sup > 0:
        as_corr_str = (f"{r.as_sup_corrigida:.2f} cm²"
                       if isinstance(r.as_sup_corrigida, float)
                       else r.as_sup_corrigida)
        bloco_sup = f"""
        <div style="margin-top: 18px; padding: 12px; background-color: #252525;
                    border-radius: 5px; text-align: center;">
            <div style="display: flex; justify-content: space-between;
                        align-items: center; margin-bottom: 8px;">
                <span style="font-size: 14pt; font-weight: bold; color: #90caf9;">
                    &#11014; Armadura Superior (A'<sub>s</sub>)</span>
                {badge(r.verifica_sup)}
            </div>
            <table style="width: 100%; font-size: 12pt; color: #e0e0e0;
                          border-collapse: collapse; text-align: center;">
                <tr><td>&Delta;&sigma; :</td><td><strong>{r.delta_sigma_sup_MPa:.2f} MPa</strong></td></tr>
                <tr><td>&Delta;f<sub>fad,sd</sub> :</td>
                    <td><strong>{r.delta_f_fad_sd_sup:.2f} MPa</strong></td></tr>
                <tr><td>k<sub>fad</sub> :</td>
                    <td><strong>{r.k_fad_sup:.4f}</strong></td></tr>
                <tr><td>A'<sub>s</sub> corrigida :</td>
                    <td><strong style="color: #90caf9;">{as_corr_str}</strong></td></tr>
            </table>
        </div>"""

    html = f"""
    <div style="font-family: sans-serif; color: #e0e0e0; padding: 18px;
                border: 1px solid #444; border-radius: 5px;
                background-color: #1e1e1e; text-align: center;">
        <div style="font-size: 16pt; font-weight: bold; margin-bottom: 16px; color: #ffffff;">
            Resultado Verificação à Fadiga - Flexão
        </div>
        <div style="display: flex; justify-content: space-around;
                    margin-bottom: 16px; font-size: 12pt;">
            <div>M&#8321; : <span style="color: #90caf9;">{r.res_M1.momento_sd:+.2f} kN.m</span></div>
            <div>M&#8322; : <span style="color: #90caf9;">{r.res_M2.momento_sd:+.2f} kN.m</span></div>
            <div>&eta;  : <span style="color: #90caf9;">{r.eta:.3f}</span></div>
        </div>
        {bloco_inf}
        {bloco_sup}
    </div>
    """
    return html


# ==============================================================================
# 5. LARGURA COLABORANTE
# ==============================================================================

def _localizar_tramo(superestrutura, x: float) -> Dict[str, Any]:
    """
    Identifica em qual vão/balanço a seção se encontra e retorna informações
    necessárias para o cálculo da largura colaborante (NBR 6118:2014, 14.6.2.2).
    """
    tipo_interno = _mapear_tipo_interno(superestrutura.tipo)
    vaos         = superestrutura.vaos

    if tipo_interno == 'biapoiada':
        comprimentos = vaos.copy()
    elif tipo_interno == 'isostatica_em_balanco':
        comprimentos = [vaos[1], vaos[0], vaos[1]]
    elif tipo_interno == 'hiperestatica_sem_balanco':
        comprimentos = [vaos[1], vaos[0], vaos[1]]
    elif tipo_interno == 'hiperestatica_com_balanco':
        comprimentos = [vaos[2], vaos[1], vaos[0], vaos[1], vaos[2]]
    else:
        raise ValueError(f"Tipo desconhecido: {tipo_interno}")

    limites = [0.0]
    for L in comprimentos:
        limites.append(limites[-1] + L)
    comp_total = limites[-1]

    if x < 0 or x > comp_total:
        return {'erro': f'Posição x={x}m fora da superestrutura (0 a {comp_total:.2f}m)'}

    idx = 0
    for i in range(len(limites) - 1):
        if limites[i] <= x <= limites[i + 1]:
            idx = i
            break

    L_tramo  = comprimentos[idx]
    x_local  = x - limites[idx]

    if tipo_interno == 'biapoiada':
        tramo_tipo = 'vao_simples'
        a = 1.0 * L_tramo
    elif tipo_interno == 'isostatica_em_balanco':
        if idx in (0, 2):
            tramo_tipo, a = 'balanco', 2.0 * L_tramo
        else:
            tramo_tipo, a = 'vao_central_continuo', 0.6 * L_tramo
    elif tipo_interno == 'hiperestatica_sem_balanco':
        if idx in (0, 2):
            tramo_tipo, a = 'vao_extremo_continuo', 0.75 * L_tramo
        else:
            tramo_tipo, a = 'vao_central_continuo', 0.6 * L_tramo
    elif tipo_interno == 'hiperestatica_com_balanco':
        if idx in (0, 4):
            tramo_tipo, a = 'balanco', 2.0 * L_tramo
        elif idx in (1, 3):
            tramo_tipo, a = 'vao_extremo_continuo_duplo_momento', 0.6 * L_tramo
        else:
            tramo_tipo, a = 'vao_central_continuo', 0.6 * L_tramo
    else:
        raise ValueError(f"Tipo interno não tratado: {tipo_interno}")

    return {
        'tramo_tipo': tramo_tipo,
        'comprimento_tramo': L_tramo,
        'a': a,
        'idx_tramo': idx,
        'x_local': x_local,
        'limites': limites,
        'erro': None,
    }


def calcular_largura_colaborante(
    superestrutura,
    secao_superestrutura,
    x: float,
    tipo_viga: str,
    d_extremidade: Optional[float] = None,
    d_eixos: Optional[float] = None,
    bw: Optional[float] = None,
) -> Tuple[str, str, float]:
    """
    Calcula a largura colaborante bf (NBR 6118:2014, 14.6.2.2).

    Retorna (memorial_str, memorial_html, bf_m).
    """
    if d_extremidade is None:
        d_extremidade = secao_superestrutura.d_extremidade / 100.0
    if d_eixos is None:
        n = secao_superestrutura.n_longarinas
        largura_total_m = secao_superestrutura.largura_total / 100.0
        d_eixos = ((largura_total_m - 2 * d_extremidade) / (n - 1)
                   if n > 1 else 0.0)
    if bw is None:
        dados_secao = secao_superestrutura.dados
        tipo_secao  = dados_secao.get("Tipo")
        if tipo_secao in ("Retangular", "T", "I"):
            bw = dados_secao.get("bw", 0.0) / 100.0
        else:
            raise ValueError("Não foi possível extrair 'bw'. Forneça explicitamente.")

    if tipo_viga not in ('extremidade', 'centro'):
        raise ValueError("tipo_viga deve ser 'extremidade' ou 'centro'")
    if d_extremidade <= 0:
        raise ValueError("d_extremidade deve ser > 0")
    if d_eixos <= 0 and tipo_viga == 'centro':
        raise ValueError("d_eixos deve ser > 0 para longarina central")
    if bw <= 0:
        raise ValueError("bw deve ser > 0")

    tramo_info = _localizar_tramo(superestrutura, x)
    if tramo_info.get('erro'):
        e = tramo_info['erro']
        return f"ERRO: {e}", f"<p style='color:red'>ERRO: {e}</p>", 0.0

    a          = tramo_info['a']
    L_tramo    = tramo_info['comprimento_tramo']
    tramo_tipo = tramo_info['tramo_tipo']

    if tipo_viga == 'centro':
        b1_geo   = d_eixos / 2.0
        b3_geo   = d_eixos / 2.0
        lado_desc = (f"viga central → d_eixos/2 = {d_eixos:.3f}/2 = {b1_geo:.3f} m")
    else:
        b1_geo   = d_extremidade
        b3_geo   = d_eixos / 2.0
        lado_desc = (f"viga de extremidade → lado externo: {d_extremidade:.3f} m; "
                     f"lado interno: d_eixos/2 = {d_eixos:.3f}/2 = {b3_geo:.3f} m")

    lim_norm = 0.1 * a
    b1 = min(b1_geo, lim_norm)
    b3 = min(b3_geo, lim_norm)
    bf = bw + b1 + b3

    # Texto simples (resumido)
    memorial_str = (
        f"LARGURA COLABORANTE (bf) – NBR 6118:2014, 14.6.2.2\n"
        f"  x = {x:.3f} m  |  Tramo: {tramo_tipo}  |  L = {L_tramo:.3f} m\n"
        f"  a = {a:.3f} m  |  0,1·a = {lim_norm:.3f} m\n"
        f"  b1 = min({b1_geo:.3f}, {lim_norm:.3f}) = {b1:.3f} m\n"
        f"  b3 = min({b3_geo:.3f}, {lim_norm:.3f}) = {b3:.3f} m\n"
        f"  bf = {bw:.3f} + {b1:.3f} + {b3:.3f} = {bf:.3f} m ({bf*100:.1f} cm)\n"
    )

    memorial_html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0;
                background-color: #1e1e1e; padding: 20px; border-radius: 8px;">
        <b style="font-size: 14pt; color: #90caf9;">Largura Colaborante (b<sub>f</sub>)</b>
        <p style="color: #b0bec5; font-size: 10pt; margin-top: 4px;">
            NBR 6118:2023 – item 14.6.2.2</p>
        <table border="0" cellspacing="4" cellpadding="4"
               style="margin-top: 12px; width: 100%;">
            <tr><td style="color:#b0bec5;">Posição x:</td>
                <td style="color:#90caf9; font-weight:700;">{x:.3f} m</td></tr>
            <tr><td style="color:#b0bec5;">Tramo:</td>
                <td style="color:#90caf9;">{tramo_tipo} (L = {L_tramo:.3f} m)</td></tr>
            <tr><td style="color:#b0bec5;">Distância a:</td>
                <td style="color:#90caf9;">{a:.3f} m</td></tr>
            <tr><td style="color:#b0bec5;">Limite normativo (0,1·a):</td>
                <td style="color:#f48fb1;">{lim_norm:.3f} m</td></tr>
            <tr><td style="color:#b0bec5;">b&#8321;:</td>
                <td style="color:#90caf9;">{b1:.3f} m</td></tr>
            <tr><td style="color:#b0bec5;">b&#8323;:</td>
                <td style="color:#90caf9;">{b3:.3f} m</td></tr>
        </table>
        <div style="margin-top: 16px; padding: 12px; background-color: #1e3a2f;
                    border-radius: 6px; text-align: center;
                    border: 1px solid #2e7d32;">
            <b style="font-size: 14pt; color: #4ade80;">
                bf = {bw:.3f} + {b1:.3f} + {b3:.3f} =
                {bf:.3f} m &nbsp;({bf*100:.1f} cm)</b>
        </div>
    </div>
    """
    return memorial_str, memorial_html, bf


def _justificativa_a(tramo_tipo: str) -> str:
    """Retorna a justificativa em texto simples para o valor de a."""
    mapa = {
        'vao_simples':                           "Viga simplesmente apoiada → a = 1,00·L",
        'balanco':                               "Tramo em balanço → a = 2,00·L",
        'vao_extremo_continuo':                  "Vão extremo de viga contínua → a = 0,75·L",
        'vao_central_continuo':                  "Vão interno/extremo c/ continuidade total → a = 0,60·L",
        'vao_extremo_continuo_duplo_momento':    "Vão extremo c/ continuidade total → a = 0,60·L",
    }
    return mapa.get(tramo_tipo, "Caso não padronizado → adotado a = 0,60·L")


def _justificativa_a_html(tramo_tipo: str) -> str:
    """Retorna a justificativa em HTML para o valor de a."""
    mapa = {
        'vao_simples':                           "Viga simplesmente apoiada → <i>a = 1,00·L</i>",
        'balanco':                               "Tramo em balanço → <i>a = 2,00·L</i>",
        'vao_extremo_continuo':                  "Vão extremo de viga contínua → <i>a = 0,75·L</i>",
        'vao_central_continuo':                  "Vão com momentos nas duas extremidades → <i>a = 0,60·L</i>",
        'vao_extremo_continuo_duplo_momento':    "Vão c/ continuidade total → <i>a = 0,60·L</i>",
    }
    return mapa.get(tramo_tipo, "Caso não padronizado → <i>a = 0,60·L</i>")


# ==============================================================================
# 6. ESPAÇAMENTO MÍNIMO
# ==============================================================================

def calcular_espacamento_minimo(diametro_barra: float, diametro_agregado: float,
                                 ativo: bool = True):
    """
    Calcula espaçamentos mínimos horizontal (ah) e vertical (av) conforme
    NBR 6118:2023, item 18.3.2.2.

    Retorna (ah_mm, av_mm, html_memorial).
    """
    ah = max(20.0, diametro_barra, 1.2 * diametro_agregado)
    av = max(20.0, diametro_barra, 0.5 * diametro_agregado)
    html = _gerar_html_espacamento(diametro_barra, diametro_agregado, ah, av, ativo)
    return ah, av, html


def _gerar_html_espacamento(diametro_barra, diametro_agregado, ah, av, ativo):
    """Gera o HTML do memorial de cálculo dos espaçamentos mínimos."""
    c_prim  = "#90caf9" if ativo else "#888888"
    c_suc   = "#4ade80" if ativo else "#888888"
    c_borda = "#333333" if ativo else "#555555"
    c_txt   = "#e0e0e0" if ativo else "#aaaaaa"
    fundo_b = "#252525" if ativo else "#2a2a2a"

    cond_h3 = 1.2 * diametro_agregado
    cond_v3 = 0.5 * diametro_agregado

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; font-size: 13pt; color: {c_txt};
                line-height: 1.6; background-color: #1e1e1e; padding: 20px;
                border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <div style="border-left: 5px solid {c_prim}; padding-left: 15px; margin-bottom: 20px;">
            <b style="font-size: 15pt; text-transform: uppercase; color: #ffffff;">
                Memorial: Espaçamento Mínimo entre Barras</b><br>
            <span style="font-size: 10pt; color: #a0a0a0;">
                Referência: ABNT NBR 6118:2023 § 18.3.2.2</span>
        </div>
        <div style="margin-bottom: 20px;">
            <b style="color: {c_prim};">1. Espaçamento Horizontal (a<sub>h</sub>):</b>
            <div style="background: {fundo_b}; padding: 15px; border-radius: 8px;
                        border: 1px solid {c_borda};">
                <div style="font-style: italic; font-size: 12pt; color: {c_txt};">
                    a<sub>h,min</sub> &ge; max(20 mm ; {diametro_barra:.2f} mm ;
                    1,2 &times; {diametro_agregado:.2f} = {cond_h3:.2f} mm)
                    = <b style="color:{c_suc};">{ah:.2f} mm</b>
                </div>
            </div>
        </div>
        <div style="margin-bottom: 20px;">
            <b style="color: {c_prim};">2. Espaçamento Vertical (a<sub>v</sub>):</b>
            <div style="background: {fundo_b}; padding: 15px; border-radius: 8px;
                        border: 1px solid {c_borda};">
                <div style="font-style: italic; font-size: 12pt; color: {c_txt};">
                    a<sub>v,min</sub> &ge; max(20 mm ; {diametro_barra:.2f} mm ;
                    0,5 &times; {diametro_agregado:.2f} = {cond_v3:.2f} mm)
                    = <b style="color:{c_suc};">{av:.2f} mm</b>
                </div>
            </div>
        </div>
        <div style="text-align: center; padding-top: 15px; border-top: 1px solid {c_borda};">
            <span style="font-size: 16pt; color: {c_suc}; font-weight: bold;">
                a<sub>h</sub> = {ah:.2f} mm &emsp; a<sub>v</sub> = {av:.2f} mm
            </span>
        </div>
    </div>
    """
    return html

