# ============================================================================
# funcoes_janela_armadura_transversal.py
# ============================================================================
# Módulo com geradores de HTML para exibição dos resultados da calculadora de
# cisalhamento (Modelo I - NBR 6118:2023) na interface gráfica.
# ============================================================================

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Tuple
import math

if TYPE_CHECKING:
    from modules.Calculadora_Cisalhamento import ResultadoCisalhamento, CalculadoraCisalhamento


def gerar_html_verificacao_biela(resultado: ResultadoCisalhamento) -> str:
    """
    Gera um bloco HTML detalhado para a verificação da biela de compressão (VRd2).

    Exibe:
      - Vsd (solicitante)
      - αv2 (fator de eficácia) com cálculo numérico
      - VRd2 (resistente) com cálculo numérico expandido
      - Comparação Vsd ≤ VRd2 com status visual (aprovado/reprovado)
      - Se houver esmagamento, exibe alerta destacado.
    """
    r = resultado

    vsd_str   = f"{r.Vsd:.2f}"
    vrd2_str  = f"{r.VRd2:.2f}"
    alpha_str = f"{r.alpha_v2:.4f}"

    # fcd em kN/cm² (dividindo por 10) para exibir na fórmula
    fcd_kNcm2 = r.fcd / 10.0

    ok = not r.esmagamento_biela

    # Cores e símbolos de status
    if ok:
        status_cor    = "#4ade80"
        status_bg     = "#166534"
        status_texto  = "✓ APROVADO"
        status_icone  = "✔️"
        comparacao_sinal = "≤"
        mensagem_extra = "A biela de compressão resiste com segurança."
    else:
        status_cor    = "#f87171"
        status_bg     = "#7f1d1d"
        status_texto  = "✗ REPROVADO"
        status_icone  = "⚠️"
        comparacao_sinal = ">"
        mensagem_extra = "RISCO DE ESMAGAMENTO DA BIELA! Aumente a seção ou o fck."

    # Alerta adicional se houver esmagamento
    alerta_html = ""
    if not ok:
        alerta_html = f"""
        <div style="margin-top: 16px; padding: 12px; background-color: #3d1a1a;
                    border-left: 5px solid #f87171; border-radius: 4px;">
            <span style="color: #f87171; font-weight: bold;">⚠️ FALHA CRÍTICA</span><br>
            <span style="color: #e0e0e0; font-size: 10pt;">
                Vsd = {vsd_str} kN > VRd2 = {vrd2_str} kN.<br>
                É necessário redimensionar a seção (aumentar bw ou d) ou utilizar
                concreto de maior resistência.
            </span>
        </div>
        """

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0;
                background-color: #1e1e1e; padding: 18px; border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <!-- Cabeçalho -->
        <div style="display: flex; justify-content: space-between; align-items: center;
                    margin-bottom: 16px;">
            <span style="font-size: 14pt; font-weight: bold; color: #90caf9;">
                🔍 Verificação da Biela de Compressão (V<sub>Rd2</sub>)
            </span>
            <span style="background-color: {status_bg}; color: {status_cor};
                         padding: 4px 12px; border-radius: 20px; font-weight: bold;
                         font-size: 12pt; border: 1px solid {status_cor};">
                {status_icone} {status_texto}
            </span>
        </div>

        <!-- Equação e parâmetros -->
        <div style="background-color: #252525; padding: 14px; border-radius: 6px;
                    margin-bottom: 16px;">
            <div style="font-size: 12pt; color: #b0bec5; margin-bottom: 10px;">
                NBR 6118:2023 – Item 17.4.2.2 (Modelo I, θ = 45°)
            </div>
            <div style="font-family: 'Courier New', monospace; font-size: 11pt;
                        color: #e0e0e0; margin-left: 10px;">
                α<sub>v2</sub> = 1 − f<sub>ck</sub>/250 = 1 − {r.fck:.1f}/250 = <b>{alpha_str}</b><br>
                V<sub>Rd2</sub> = 0,27 · α<sub>v2</sub> · f<sub>cd</sub> · b<sub>w</sub> · d <br>
                &nbsp;&nbsp;= 0,27 · {alpha_str} · ({r.fcd:.3f}/10) · {r.bw:.2f} · {r.d:.2f}<br>
                &nbsp;&nbsp;= <b>{vrd2_str} kN</b>
            </div>
        </div>

        <!-- Tabela de valores -->
        <table style="width: 100%; border-collapse: collapse; margin: 12px 0;">
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 8px 0; color: #b0bec5; font-size: 12pt;">V<sub>sd</sub> (solicitante)</td>
                <td style="padding: 8px 0; text-align: right; color: #90caf9;
                           font-weight: bold; font-size: 12pt;">{vsd_str} kN</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 8px 0; color: #b0bec5; font-size: 12pt;">V<sub>Rd2</sub> (resistente)</td>
                <td style="padding: 8px 0; text-align: right; color: #90caf9;
                           font-weight: bold; font-size: 12pt;">{vrd2_str} kN</td>
            </tr>
        </table>

        <!-- Comparação -->
        <div style="background-color: {status_bg}; padding: 14px; border-radius: 6px;
                    text-align: center; margin-top: 10px; border: 1px solid {status_cor};">
            <span style="font-size: 13pt; color: #ffffff;">
                V<sub>sd</sub> = {vsd_str} kN  {comparacao_sinal}  V<sub>Rd2</sub> = {vrd2_str} kN
            </span>
            <div style="font-size: 11pt; color: {status_cor}; margin-top: 6px;">
                {mensagem_extra}
            </div>
        </div>

        {alerta_html}

        <!-- Nota complementar -->
        <div style="margin-top: 14px; font-size: 9pt; color: #888; text-align: right;">
            f<sub>cd</sub> = {r.fcd:.3f} MPa &nbsp;|&nbsp;
            b<sub>w</sub> = {r.bw:.2f} cm &nbsp;|&nbsp; d = {r.d:.2f} cm
        </div>
    </div>
    """
    return html


def gerar_html_resumo_dimensionamento(resultado: ResultadoCisalhamento) -> str:
    """
    Gera um bloco HTML com o resumo do dimensionamento da armadura transversal.

    Exibe:
      - Vc (parcela do concreto)
      - Vsw (parcela a ser absorvida pela armadura)
      - Asw/s calculado
      - Asw/s mínimo
      - Asw/s a adotar (máximo entre calculado e mínimo) com 2 casas decimais
      - Alertas informativos (ex.: "concreto absorve todo o cisalhamento")
    """
    r = resultado

    # Formata valores
    vc_str   = f"{r.Vc:.2f}"
    vsw_str  = f"{r.Vsw:.2f}"
    calc_str = f"{r.asw_calc_cm2_m:.4f}"
    min_str  = f"{r.asw_min_cm2_m:.4f}"
    adot_str = f"{r.asw_adotar_cm2_m:.2f}"   # 2 casas decimais conforme solicitado

    # Determina se a armadura calculada é menor que a mínima
    usa_min = r.asw_adotar_cm2_m == r.asw_min_cm2_m and r.asw_calc_cm2_m < r.asw_min_cm2_m

    # Monta alertas informativos (caso existam)
    alertas_html = ""
    if r.alertas:
        alertas_html = '<div style="margin-top: 16px;">'
        for al in r.alertas:
            cor_alerta = "#fbbf24" if "INFO" in al else "#f87171"
            alertas_html += f"""
            <div style="background-color: #252525; padding: 8px 12px; margin-bottom: 6px;
                        border-left: 4px solid {cor_alerta}; border-radius: 2px;
                        font-size: 10pt; color: #e0e0e0;">
                ⚠️ {al}
            </div>
            """
        alertas_html += '</div>'

    # Destacar se houver esmagamento (já tratado em outra função, mas reforçar)
    if r.esmagamento_biela:
        alertas_html += """
        <div style="margin-top: 12px; background-color: #3d1a1a; padding: 8px;
                    border-radius: 4px; color: #f87171; font-weight: bold;
                    text-align: center;">
            ⚠️ ATENÇÃO: Esmagamento da biela detectado. O dimensionamento da armadura
            pode não ser válido.
        </div>
        """

    # Texto adicional quando Vsw = 0
    obs_concreto = ""
    if r.Vsw < 1e-9:
        obs_concreto = """
        <div style="margin-top: 12px; padding: 8px; background-color: #1e3a2f;
                    border-radius: 4px; color: #4ade80; font-size: 10pt;
                    text-align: center;">
            ℹ️ O concreto sozinho resiste ao cisalhamento (Vc ≥ Vsd).<br>
            Será adotada apenas a armadura mínima normativa.
        </div>
        """

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0;
                background-color: #1e1e1e; padding: 18px; border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <!-- Título -->
        <div style="font-size: 14pt; font-weight: bold; color: #90caf9;
                    margin-bottom: 16px; border-bottom: 1px solid #444;
                    padding-bottom: 8px;">
            📊 Dimensionamento da Armadura Transversal (Modelo I)
        </div>

        <!-- Tabela de resultados -->
        <table style="width: 100%; border-collapse: collapse; font-size: 12pt;">
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 10px 0; color: #b0bec5;">V<sub>c</sub> (parcela do concreto)</td>
                <td style="padding: 10px 0; text-align: right; color: #90caf9;
                           font-weight: bold;">{vc_str} kN</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 10px 0; color: #b0bec5;">V<sub>sw</sub> (parcela da armadura)</td>
                <td style="padding: 10px 0; text-align: right; color: #90caf9;
                           font-weight: bold;">{vsw_str} kN</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 10px 0; color: #b0bec5;">A<sub>sw</sub>/s (calculado)</td>
                <td style="padding: 10px 0; text-align: right; color: #f48fb1;
                           font-weight: bold;">{calc_str} cm²/m</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 10px 0; color: #b0bec5;">A<sub>sw</sub>/s (mínimo)</td>
                <td style="padding: 10px 0; text-align: right; color: #f48fb1;
                           font-weight: bold;">{min_str} cm²/m</td>
            </tr>
        </table>

        <!-- Bloco de destaque para o valor adotado -->
        <div style="margin-top: 20px; background-color: #252525; padding: 14px;
                    border-radius: 6px; text-align: center;
                    border: 1px solid #4ade80;">
            <span style="font-size: 11pt; color: #b0bec5;">ARMADURA A ADOTAR</span><br>
            <span style="font-size: 18pt; font-weight: bold; color: #4ade80;">
                A<sub>sw</sub>/s = {adot_str} cm²/m
            </span>
            {f'<div style="font-size: 9pt; color: #888; margin-top: 6px;">(adotado o valor mínimo normativo)</div>' if usa_min else ''}
        </div>

        {obs_concreto}
        {alertas_html}

        <!-- Rodapé com inclinação dos estribos -->
        <div style="margin-top: 14px; font-size: 9pt; color: #888; text-align: right;">
            Estribos inclinados a α = {r.alpha_graus:.1f}° &nbsp;|&nbsp;
            f<sub>ywd</sub> = {r.fywd:.3f} MPa
        </div>
    </div>
    """
    return html


def gerar_html_espacamento_estribos(
    asw_necessario: float,
    d_cm: float,
    diametro_mm: float,
    n_ramos: int = 2,
    fyk: float = 500.0
) -> Tuple[float, str]:
    """
    Calcula o espaçamento dos estribos com base na armadura transversal necessária
    e gera um memorial de cálculo detalhado em HTML.

    Parâmetros
    ----------
    asw_necessario : float
        Armadura transversal necessária em cm²/m (Asw/s).
    d_cm : float
        Altura útil da seção em cm (usada para verificação do espaçamento máximo).
    diametro_mm : float
        Diâmetro nominal do estribo em mm (ex: 6.3, 8.0, 10.0).
    n_ramos : int, opcional
        Número de ramos do estribo (padrão 2 para estribo simples).
    fyk : float, opcional
        Resistência característica do aço em MPa (padrão 500). Exibido apenas no rodapé.

    Retorna
    -------
    Tuple[float, str]
        - Espaçamento final recomendado (cm), limitado ao máximo normativo se necessário.
        - Código HTML estilizado com o memorial de cálculo.
    """
    # Tratamento para asw_necessario <= 0
    if asw_necessario <= 0.0:
        # Sem necessidade de armadura transversal, espaçamento tende ao infinito.
        # Retornamos o limite máximo normativo como valor seguro, embora não seja exigido.
        s_max_norma = min(0.6 * d_cm, 30.0)
        s_final_seguro = s_max_norma

        # Geração de HTML simplificado para este caso
        html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0;
                    background-color: #1e1e1e; padding: 18px; border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
            <div style="font-size: 14pt; font-weight: bold; color: #90caf9;
                        margin-bottom: 16px;">
                📏 Espaçamento dos Estribos
            </div>
            <div style="background-color: #1e3a2f; padding: 14px; border-radius: 6px;
                        text-align: center; border: 1px solid #4ade80;">
                <span style="color: #4ade80; font-size: 12pt;">
                    ℹ️ A armadura transversal necessária (A<sub>sw</sub>/s) é nula ou negativa.<br>
                    Não há exigência de estribos para cisalhamento. Apenas armadura mínima
                    ou construtiva se aplica.
                </span>
            </div>
        </div>
        """
        return s_final_seguro, html

    # 1. Converter diâmetro para cm
    diametro_cm = diametro_mm / 10.0

    # 2. Área de uma barra (π·φ²/4)
    area_1_barra_cm2 = math.pi * (diametro_cm ** 2) / 4.0

    # 3. Área total da seção do estribo (n ramos)
    area_estribo_cm2 = n_ramos * area_1_barra_cm2

    # 4. Espaçamento calculado (cm)
    s_calculado = (area_estribo_cm2 / asw_necessario) * 100.0

    # 5. Arredondar para baixo com precisão de 0,5 cm
    s_final = math.floor(s_calculado * 2) / 2.0

    # 6. Verificação do espaçamento máximo permitido (NBR 6118:2023, 18.3.4.1)
    s_max_norma = min(0.6 * d_cm, 30.0)
    excede_maximo = s_final > s_max_norma

    s_final_seguro = s_max_norma if excede_maximo else s_final

    # =========================================================================
    # GERAÇÃO DO HTML
    # =========================================================================
    cor_destaque = "#4ade80" if not excede_maximo else "#f87171"
    cor_borda    = "#4ade80" if not excede_maximo else "#f87171"
    bg_destaque  = "#1e3a2f" if not excede_maximo else "#3d1a1a"

    phi_str        = f"{diametro_mm:.1f}".rstrip('0').rstrip('.')
    asw_str        = f"{asw_necessario:.2f}"
    area_1_str     = f"{area_1_barra_cm2:.4f}"
    area_est_str   = f"{area_estribo_cm2:.4f}"
    s_calc_str     = f"{s_calculado:.3f}"
    s_final_str    = f"{s_final:.1f}".rstrip('0').rstrip('.')
    s_max_str      = f"{s_max_norma:.1f}".rstrip('0').rstrip('.')
    s_final_seguro_str = f"{s_final_seguro:.1f}".rstrip('0').rstrip('.')

    alerta_html = ""
    if excede_maximo:
        alerta_html = f"""
        <div style="margin-top: 16px; padding: 12px; background-color: #3d1a1a;
                    border-left: 5px solid #f87171; border-radius: 4px;">
            <span style="color: #f87171; font-weight: bold;">⚠️ ATENÇÃO</span><br>
            <span style="color: #e0e0e0; font-size: 10pt;">
                O espaçamento calculado (s = {s_final_str} cm) excede o limite máximo
                normativo de {s_max_str} cm (NBR 6118:2023, 18.3.4.1).<br>
                <b>Recomenda-se adotar s = {s_final_seguro_str} cm</b> ou 
                <b>reduzir o diâmetro da barra / reduzir o número de ramos</b> 
                para adequar o espaçamento.
            </span>
        </div>
        """

    arredondamento_msg = f"""
    <div style="margin-top: 10px; font-size: 9pt; color: #888;">
        Arredondamento para baixo com tolerância de 0,5 cm:<br>
        s<sub>calculado</sub> = {s_calc_str} cm → floor({s_calc_str} × 2) / 2 = {s_final_str} cm
    </div>
    """

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0;
                background-color: #1e1e1e; padding: 18px; border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <div style="display: flex; justify-content: space-between; align-items: center;
                    margin-bottom: 16px;">
            <span style="font-size: 14pt; font-weight: bold; color: #90caf9;">
                📏 Espaçamento dos Estribos
            </span>
            <span style="font-size: 10pt; color: #b0bec5;">
                NBR 6118:2023 – Item 18.3.4.1
            </span>
        </div>

        <div style="background-color: #252525; padding: 14px; border-radius: 6px;
                    margin-bottom: 16px;">
            <div style="font-size: 12pt; color: #b0bec5; margin-bottom: 10px;">
                Dados de Entrada
            </div>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 4px 0; color: #b0bec5;">A<sub>sw</sub>/s necessário</td>
                    <td style="padding: 4px 0; text-align: right; color: #90caf9;
                               font-weight: bold;">{asw_str} cm²/m</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #b0bec5;">Altura útil (d)</td>
                    <td style="padding: 4px 0; text-align: right; color: #90caf9;
                               font-weight: bold;">{d_cm:.2f} cm</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #b0bec5;">Diâmetro do estribo (ϕ)</td>
                    <td style="padding: 4px 0; text-align: right; color: #90caf9;
                               font-weight: bold;">{phi_str} mm</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #b0bec5;">Número de ramos</td>
                    <td style="padding: 4px 0; text-align: right; color: #90caf9;
                               font-weight: bold;">{n_ramos}</td>
                </tr>
            </table>
        </div>

        <div style="background-color: #252525; padding: 14px; border-radius: 6px;
                    margin-bottom: 16px;">
            <div style="font-size: 12pt; color: #b0bec5; margin-bottom: 10px;">
                Cálculo do Espaçamento
            </div>
            <div style="font-family: 'Courier New', monospace; font-size: 11pt;
                        color: #e0e0e0; margin-left: 10px;">
                1) Área de uma barra: A₁ = π·ϕ²/4 = π·({diametro_cm:.3f})²/4 = {area_1_str} cm²<br>
                2) Área total do estribo: A<sub>est</sub> = n_ramos · A₁ = {n_ramos} · {area_1_str} = {area_est_str} cm²<br>
                3) Espaçamento calculado: s<sub>calc</sub> = (A<sub>est</sub> / A<sub>sw</sub>) · 100<br>
                &nbsp;&nbsp;&nbsp;= ({area_est_str} / {asw_str}) · 100 = {s_calc_str} cm
            </div>
            {arredondamento_msg}
        </div>

        <div style="background-color: {bg_destaque}; padding: 14px; border-radius: 6px;
                    text-align: center; border: 1px solid {cor_borda};">
            <span style="font-size: 11pt; color: #b0bec5;">ESPAÇAMENTO FINAL (arredondado p/ 0,5 cm)</span><br>
            <span style="font-size: 18pt; font-weight: bold; color: {cor_destaque};">
                s = {s_final_str} cm
            </span>
        </div>

        <div style="margin-top: 16px; padding: 10px; background-color: #252525;
                    border-radius: 4px;">
            <span style="color: #b0bec5; font-size: 10pt;">
                Espaçamento máximo permitido (NBR 6118:2023, 18.3.4.1):<br>
                s<sub>max</sub> = min(0,6·d ; 30 cm) = min(0,6·{d_cm:.1f} ; 30) = {s_max_str} cm
            </span>
        </div>

        {alerta_html}

        <div style="margin-top: 14px; font-size: 9pt; color: #888; text-align: right;">
            d = {d_cm:.2f} cm &nbsp;|&nbsp; f<sub>yk</sub> = {fyk:.1f} MPa
        </div>
    </div>
    """

    return s_final_seguro, html


# ==============================================================================
# AMPLITUDE DE TENSÃO ADMISSÍVEL PARA ESTRIBOS (NBR 6118:2023 – TABELA 23.2)
# ==============================================================================

def calcular_delta_fad_estribo(diametro_mm: float,
                               diametro_pino_mm: float = None,
                               condicao: str = 'padrao',
                               ativo: bool = True):
    """
    Calcula a amplitude de tensão admissível Δf_sd,fad para estribos de aço CA-50,
    conforme a Tabela 23.2 da NBR 6118:2023.

    Parâmetros:
    - diametro_mm: Diâmetro nominal do estribo (mm).
    - diametro_pino_mm: Diâmetro do pino de dobramento (mm). Se omitido, adota-se
                        a condição conservadora D ≥ 5ϕ para ϕ < 20 mm ou D ≥ 8ϕ
                        para ϕ ≥ 20 mm.
    - condicao: 'padrao' (estribo dobrado), 'soldada' (barra soldada ou conector
                mecânico), 'marinho' (ambiente marinho ou Classe IV).
    - ativo: Controla as cores do HTML (True = tema claro/ativo, False = tema escuro).

    Retorna:
    - delta (float): Valor de Δf_sd,fad em MPa.
    - html (str): Memorial de cálculo formatado em HTML.
    """

    # ========== TABELAS AUXILIARES (NBR 6118:2023) ==========
    # Caso 1: Barras retas ou dobradas com D ≥ 25ϕ (vale para estribos com dobra muito generosa)
    tabela_reta = {
        10.0: 190, 12.5: 190, 16.0: 190, 20.0: 185,
        22.0: 180, 25.0: 175, 32.0: 165, 40.0: 150
    }

    # Caso 2: Estribos com D < 25ϕ e D ≥ 8ϕ (valores decrescentes)
    tabela_8phi = {
        10.0: 105, 12.5: 105, 16.0: 105, 20.0: 105,
        22.0: 100, 25.0: 95, 32.0: 90, 40.0: 85
    }

    # Caso 3: Estribos com D ≥ 5ϕ e ϕ < 20 mm
    tabela_5phi = {
        10.0: 90, 12.5: 90, 16.0: 90
    }

    # ========== FUNÇÃO DE INTERPOLAÇÃO LINEAR ==========
    def interpolar(tabela, x):
        if x in tabela:
            return tabela[x]
        chaves = sorted(tabela.keys())
        if x < chaves[0]:
            x1, x2 = chaves[0], chaves[1]
        elif x > chaves[-1]:
            x1, x2 = chaves[-2], chaves[-1]
        else:
            for i in range(len(chaves) - 1):
                if chaves[i] <= x <= chaves[i + 1]:
                    x1, x2 = chaves[i], chaves[i + 1]
                    break
        y1, y2 = tabela[x1], tabela[x2]
        return y1 + (x - x1) * (y2 - y1) / (x2 - x1)

    # ========== DETERMINAÇÃO DO VALOR Δf ==========
    categoria = ""
    justificativa = ""

    # Casos especiais têm precedência
    if condicao == 'soldada':
        delta = 85.0
        categoria = "Barras soldadas ou conectores mecânicos"
        justificativa = "Valor fixo de 85 MPa conforme Tabela 23.2."
    elif condicao == 'marinho':
        delta = 110.0
        categoria = "Ambiente marinho / Classe de Agressividade IV"
        justificativa = "Valor fixo de 110 MPa independente do diâmetro."
    else:
        # Determinação pela relação D/ϕ
        if diametro_pino_mm is not None:
            razao = diametro_pino_mm / diametro_mm
            if razao >= 25.0:
                delta = interpolar(tabela_reta, diametro_mm)
                categoria = f"Barras retas ou dobradas com D ≥ 25ϕ (D/ϕ = {razao:.1f})"
                justificativa = "Dobramento com raio generoso, comportamento igual ao de barras retas."
            elif razao >= 8.0:
                delta = interpolar(tabela_8phi, diametro_mm)
                categoria = f"Estribos com D < 25ϕ e D ≥ 8ϕ (D/ϕ = {razao:.1f})"
                justificativa = "Valores decrescentes conforme diâmetro."
            elif razao >= 5.0:
                if diametro_mm < 20.0:
                    delta = interpolar(tabela_5phi, diametro_mm)
                    categoria = f"Estribos com D ≥ 5ϕ e ϕ < 20 mm (D/ϕ = {razao:.1f})"
                    justificativa = "Valor constante de 90 MPa para ϕ10 a ϕ16."
                else:
                    delta = interpolar(tabela_8phi, diametro_mm)
                    categoria = f"Estribos com D ≥ 5ϕ e ϕ ≥ 20 mm (D/ϕ = {razao:.1f})"
                    justificativa = "Para ϕ ≥ 20 mm, adota-se a mesma tabela de D ≥ 8ϕ."
            elif razao >= 3.0 and diametro_mm <= 10.0:
                delta = 85.0
                categoria = f"Estribos com D ≥ 3ϕ e ϕ ≤ 10 mm (D/ϕ = {razao:.1f})"
                justificativa = "Valor mínimo permitido para estribos de pequeno diâmetro."
            else:
                raise ValueError("Relação D/ϕ não atende aos mínimos normativos (D ≥ 3ϕ para ϕ ≤ 10 mm, D ≥ 5ϕ para ϕ < 20 mm, D ≥ 8ϕ para ϕ ≥ 20 mm).")
        else:
            # Sem informação do pino, adota-se o caso conservador mais comum: D ≥ 5ϕ
            if diametro_mm < 20.0:
                delta = interpolar(tabela_5phi, diametro_mm)
                categoria = "Estribos com D ≥ 5ϕ e ϕ < 20 mm (assumido automaticamente)"
                justificativa = "Como o diâmetro do pino não foi informado, adotou-se a condição usual de dobramento conforme Tabela 9.1 da NBR 6118 (D ≥ 5ϕ)."
            else:
                delta = interpolar(tabela_8phi, diametro_mm)
                categoria = "Estribos com D ≥ 8ϕ e ϕ ≥ 20 mm (assumido automaticamente)"
                justificativa = "Para ϕ ≥ 20 mm, a norma exige D ≥ 8ϕ. Valor interpolado da tabela correspondente."

    # ========== GERAÇÃO DO HTML ==========
    html = _gerar_html_estribo(diametro_mm, diametro_pino_mm, delta, categoria,
                               justificativa, condicao, ativo)
    return delta, html


def _gerar_html_estribo(diametro_mm, diametro_pino_mm, delta, categoria,
                        justificativa, condicao, ativo):
    """Gera o HTML do memorial de cálculo para estribos."""

    # Definição de cores conforme estado ativo
    c_prim  = "#90caf9" if ativo else "#888888"
    c_suc   = "#4ade80" if ativo else "#888888"
    c_borda = "#333333" if ativo else "#555555"
    c_txt   = "#e0e0e0" if ativo else "#aaaaaa"
    fundo_b = "#252525" if ativo else "#2a2a2a"
    c_tit   = "#ffffff" if ativo else "#cccccc"

    # Strings formatadas
    diam_str = f"{diametro_mm:.1f} mm"
    pino_str = f"{diametro_pino_mm:.1f} mm" if diametro_pino_mm is not None else "não informado"
    delta_str = f"{delta:.1f} MPa"
    condicao_str = condicao.capitalize()

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; font-size: 13pt; color: {c_txt};
                line-height: 1.6; background-color: #1e1e1e; padding: 20px;
                border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <div style="border-left: 5px solid {c_prim}; padding-left: 15px; margin-bottom: 20px;">
            <b style="font-size: 15pt; text-transform: uppercase; color: {c_tit};">
                Memorial: Amplitude de Tensão Admissível (Δf<sub>sd,fad</sub>) – Estribos</b><br>
            <span style="font-size: 10pt; color: #a0a0a0;">
                Referência: ABNT NBR 6118:2023 – Tabela 23.2</span>
        </div>

        <div style="background: {fundo_b}; padding: 15px; border-radius: 8px;
                    border: 1px solid {c_borda}; margin-bottom: 20px;">
            <div style="font-style: italic; font-size: 12pt; margin-bottom: 10px; color: {c_txt};">
                <b>• Diâmetro do estribo (ϕ):</b> {diam_str}<br>
                <b>• Diâmetro do pino de dobramento (D):</b> {pino_str}<br>
                <b>• Condição especial:</b> {condicao_str}
            </div>
            <div style="margin-top: 15px; padding-top: 10px; border-top: 1px dashed {c_borda};">
                <b style="color: {c_prim};">Classificação adotada:</b><br>
                <span style="color: {c_txt};">{categoria}</span><br>
                <span style="font-size: 11pt; color: #b0b0b0;">{justificativa}</span>
            </div>
        </div>

        <div style="background: {fundo_b}; padding: 20px; border-radius: 8px;
                    border: 1px solid {c_borda}; text-align: center;">
            <span style="font-size: 14pt; color: {c_txt};">Amplitude admissível:</span>
            <div style="font-size: 32pt; font-weight: bold; color: {c_suc};
                        margin: 10px 0; letter-spacing: 2px;">
                Δf<sub>sd,fad</sub> = {delta_str}
            </div>
            <span style="font-size: 10pt; color: #a0a0a0;">
                Valor para 2×10<sup>6</sup> ciclos – Curva S-N (Woeller)
            </span>
        </div>

        <div style="margin-top: 15px; font-size: 10pt; color: #a0a0a0; text-align: right;">
            * Interpolação linear aplicada quando necessário.
        </div>
    </div>
    """
    return html


import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.Calculadora_Cisalhamento_Fadiga import ResultadoFadigaCisalhamento


def gerar_html_resumo_fadiga(resultado: ResultadoFadigaCisalhamento) -> str:
    """
    Gera um bloco HTML compacto com os resultados principais da verificação à
    fadiga da armadura transversal (NBR 6118:2023, Item 23.5.3).

    Exibe:
      - Esforços cortantes de serviço (Vd1,serv e Vd2,serv)
      - Vc,fad (parcela reduzida do concreto)
      - Tensões nos estribos (σsw1 e σsw2)
      - Amplitude de tensão (Δσsw)
      - Fator de fadiga (kfad) com status visual
      - Armadura corrigida (se necessário) e valor final a adotar

    Args:
        resultado: Objeto ResultadoFadigaCisalhamento preenchido pela calculadora.

    Returns:
        str: Código HTML estilizado para inserção em QLabel (RichText).
    """
    r = resultado

    # Status e cores
    ok = r.verifica
    if ok:
        status_cor    = "#4ade80"
        status_bg     = "#166534"
        status_texto  = "✓ APROVADO À FADIGA"
        status_icone  = "✔️"
    else:
        status_cor    = "#f87171"
        status_bg     = "#7f1d1d"
        status_texto  = "✗ REPROVADO À FADIGA"
        status_icone  = "⚠️"

    # Formatação de valores (armaduras com 2 casas decimais)
    vd1_str     = f"{r.Vd1_serv:+.2f}"
    vd2_str     = f"{r.Vd2_serv:+.2f}"
    vc_fad_str  = f"{r.Vc_fadiga:.2f}"
    sw1_str     = f"{r.sigma_sw1:.2f}"
    sw2_str     = f"{r.sigma_sw2:.2f}"
    delta_str   = f"{r.delta_sigma_sw:.2f}"
    kfad_str    = f"{r.kfad:.4f}"
    asw_elu_str = f"{r.asw_s_adotado:.2f}"
    asw_fad_str = f"{r.asw_s_fadiga:.2f}"
    asw_final_str = f"{r.asw_s_final:.2f}"

    # Informação sobre sinal dos esforços
    if r.sinais_opostos:
        sinal_msg = "Sinais opostos → σ<sub>sw,min</sub> = 0"
    else:
        sinal_msg = "Mesmo sinal → Δσ<sub>sw</sub> = |σ<sub>sw1</sub> − σ<sub>sw2</sub>|"

    # Mensagem de correção de armadura
    correcao_html = ""
    if not ok:
        correcao_html = f"""
        <div style="margin-top: 12px; padding: 8px; background-color: #3d1a1a;
                    border-radius: 4px; text-align: center;">
            <span style="color: #f87171; font-size: 11pt;">
                ⚠️ Armadura majorada por fadiga:<br>
                A<sub>sw,fad</sub> = k<sub>fad</sub> · A<sub>sw,ELU</sub> = {r.kfad:.4f} · {r.asw_s_adotado:.2f} = {r.asw_s_fadiga:.2f} cm²/m
            </span>
        </div>
        """

    # Alerta sobre sinais opostos (informativo)
    info_sinal = ""
    if r.sinais_opostos:
        info_sinal = """
        <div style="margin-top: 8px; font-size: 9pt; color: #fbbf24; text-align: center;">
            ℹ️ Inversão de sinal do cortante → σ<sub>sw,min</sub> = 0
        </div>
        """

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #e0e0e0;
                background-color: #1e1e1e; padding: 18px; border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <!-- Cabeçalho com status -->
        <div style="display: flex; justify-content: space-between; align-items: center;
                    margin-bottom: 16px;">
            <span style="font-size: 14pt; font-weight: bold; color: #90caf9;">
                🔄 Fadiga da Armadura Transversal
            </span>
            <span style="background-color: {status_bg}; color: {status_cor};
                         padding: 4px 12px; border-radius: 20px; font-weight: bold;
                         font-size: 12pt; border: 1px solid {status_cor};">
                {status_icone} {status_texto}
            </span>
        </div>

        <!-- Tabela principal -->
        <table style="width: 100%; border-collapse: collapse; font-size: 11pt;">
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 6px 0; color: #b0bec5;">V<sub>d1,serv</sub></td>
                <td style="padding: 6px 0; text-align: right; color: #90caf9;
                           font-weight: bold;">{vd1_str} kN</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 6px 0; color: #b0bec5;">V<sub>d2,serv</sub></td>
                <td style="padding: 6px 0; text-align: right; color: #90caf9;
                           font-weight: bold;">{vd2_str} kN</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 6px 0; color: #b0bec5;">V<sub>c,fad</sub> (0,5·V<sub>c</sub>)</td>
                <td style="padding: 6px 0; text-align: right; color: #90caf9;
                           font-weight: bold;">{vc_fad_str} kN</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 6px 0; color: #b0bec5;">σ<sub>sw1</sub></td>
                <td style="padding: 6px 0; text-align: right; color: #f48fb1;
                           font-weight: bold;">{sw1_str} MPa</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 6px 0; color: #b0bec5;">σ<sub>sw2</sub></td>
                <td style="padding: 6px 0; text-align: right; color: #f48fb1;
                           font-weight: bold;">{sw2_str} MPa</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 6px 0; color: #b0bec5;">Δσ<sub>sw</sub></td>
                <td style="padding: 6px 0; text-align: right; color: #f48fb1;
                           font-weight: bold;">{delta_str} MPa</td>
            </tr>
            <tr style="border-bottom: 1px solid #444;">
                <td style="padding: 6px 0; color: #b0bec5;">Δf<sub>sd,fad</sub> (Tab. 23.2)</td>
                <td style="padding: 6px 0; text-align: right; color: #b0bec5;">{r.delta_fsd_fad:.1f} MPa</td>
            </tr>
            <tr style="border-bottom: 1px solid #555;">
                <td style="padding: 6px 0; color: #b0bec5; font-weight: bold;">k<sub>fad</sub></td>
                <td style="padding: 6px 0; text-align: right; color: {status_cor};
                           font-weight: bold; font-size: 13pt;">{kfad_str}</td>
            </tr>
        </table>

        {info_sinal}

        <!-- Bloco de armadura final -->
        <div style="margin-top: 20px; background-color: #252525; padding: 14px;
                    border-radius: 6px; text-align: center;
                    border: 1px solid {status_cor};">
            <span style="font-size: 11pt; color: #b0bec5;">ARMADURA TRANSVERSAL FINAL</span><br>
            <span style="font-size: 18pt; font-weight: bold; color: {status_cor};">
                A<sub>sw</sub>/s = {asw_final_str} cm²/m
            </span>
            <div style="font-size: 9pt; color: #888; margin-top: 6px;">
                (ELU: {asw_elu_str} cm²/m | Fadiga: {asw_fad_str} cm²/m)
            </div>
        </div>

        {correcao_html}

        <!-- Rodapé com norma -->
        <div style="margin-top: 14px; font-size: 9pt; color: #888; text-align: right;">
            NBR 6118:2023 – Item 23.5.3 &nbsp;|&nbsp; Modelo I
        </div>
    </div>
    """
    return html


# ============================================================================
# BLOCO DE TESTES ROBUSTOS (CORRIGIDO)
# ============================================================================
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from modules.Calculadora_Cisalhamento_Fadiga import (
        CalculadoraCisalhamentoFadiga,
        AcoesFadigaCisalhamento
    )

    print("=" * 80)
    print("TESTES DA FUNÇÃO HTML PARA FADIGA DA ARMADURA TRANSVERSAL")
    print("=" * 80)

    calc = CalculadoraCisalhamentoFadiga(gamma_c=1.4, delta_fsd_fad=85.0)

    # -------------------------------------------------------------------------
    # TESTE 1: Exemplo 1 – Viga T (slide 25-30)
    # -------------------------------------------------------------------------
    print("\n[TESTE 1] Exemplo 1 – Viga T (kfad > 1, requer majoração)")
    res1 = calc.verificar_fadiga(
        bw=80.0,
        d=208.0,
        asw_s_adotado=18.4,
        fck=30.0,
        Vd1_serv=-1553.0,
        Vd2_serv=-965.0,
    )
    html1 = gerar_html_resumo_fadiga(res1)
    with open("teste_fadiga_exemplo1.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html1}</body></html>")
    print("  → Arquivo 'teste_fadiga_exemplo1.html' gerado.")

    # Verificações (usando atributos do resultado, não strings HTML)
    assert res1.verifica is False
    assert res1.kfad > 1.0
    assert abs(res1.asw_s_fadiga - 36.98) < 0.5
    assert "REPROVADO" in html1  # ainda confiável pois é texto fixo
    print("  ✓ Teste passou (reprovado, kfad > 1).")

    # -------------------------------------------------------------------------
    # TESTE 2: Exemplo 2 – Seção S10,dir (slide 31-37)
    # -------------------------------------------------------------------------
    print("\n[TESTE 2] Exemplo 2 – Seção S10,dir (também reprovado, kfad > 1)")
    res2 = calc.verificar_fadiga(
        bw=60.0,
        d=155.0,
        asw_s_adotado=21.0,
        fck=30.0,
        Vd1_serv=1029.3,
        Vd2_serv=573.2,
    )
    html2 = gerar_html_resumo_fadiga(res2)
    with open("teste_fadiga_exemplo2.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html2}</body></html>")
    print("  → Arquivo 'teste_fadiga_exemplo2.html' gerado.")

    assert res2.verifica is False
    assert res2.kfad > 1.0
    assert abs(res2.asw_s_fadiga - 38.43) < 0.5
    assert "REPROVADO" in html2
    print("  ✓ Teste passou.")

    # -------------------------------------------------------------------------
    # TESTE 3: Caso aprovado (kfad ≤ 1)
    # -------------------------------------------------------------------------
    print("\n[TESTE 3] Cenário com kfad ≤ 1 (aprovado)")
    res3 = calc.verificar_fadiga(
        bw=50.0,
        d=100.0,
        asw_s_adotado=50.0,
        fck=30.0,
        Vd1_serv=500.0,
        Vd2_serv=200.0,
    )
    html3 = gerar_html_resumo_fadiga(res3)
    with open("teste_fadiga_aprovado.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html3}</body></html>")
    print("  → Arquivo 'teste_fadiga_aprovado.html' gerado.")

    assert res3.verifica is True
    assert res3.kfad <= 1.0
    assert "APROVADO" in html3
    print("  ✓ Teste passou (aprovado).")

    # -------------------------------------------------------------------------
    # TESTE 4: Sinais opostos
    # -------------------------------------------------------------------------
    print("\n[TESTE 4] Caso com inversão de sinal (sinais opostos)")
    res4 = calc.verificar_fadiga(
        bw=60.0,
        d=120.0,
        asw_s_adotado=25.0,
        fck=30.0,
        Vd1_serv=800.0,
        Vd2_serv=-300.0,
    )
    html4 = gerar_html_resumo_fadiga(res4)
    with open("teste_fadiga_sinais_opostos.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html4}</body></html>")
    print("  → Arquivo 'teste_fadiga_sinais_opostos.html' gerado.")

    assert res4.sinais_opostos is True
    # Verifica se a indicação de inversão aparece (pode ser texto ou tag)
    assert "Inversão" in html4 or "Sinais opostos" in html4
    print("  ✓ Teste passou (indicação de sinais opostos presente).")

    # -------------------------------------------------------------------------
    # TESTE 5: Verificação de arredondamento (2 casas decimais nas armaduras)
    # -------------------------------------------------------------------------
    print("\n[TESTE 5] Arredondamento para 2 casas decimais")
    # Usa o resultado do teste 2 para inspecionar strings formatadas
    # As strings devem conter duas casas decimais (ex: "21.00" e não "21.0000")
    assert f"{res2.asw_s_adotado:.2f}" in html2
    assert f"{res2.asw_s_fadiga:.2f}" in html2
    print("  ✓ Formatação com 2 casas decimais confirmada.")

    print("\n" + "=" * 80)
    print("✅ Todos os testes da função HTML de fadiga concluídos com sucesso.")
    print("=" * 80)
"""
# ============================================================================
# BLOCO DE TESTES ROBUSTOS (HTMLs SEPARADOS)
# ============================================================================
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from modules.Calculadora_Cisalhamento import (
        CalculadoraCisalhamento,
        AcoesCisalhamento
    )

    print("=" * 80)
    print("TESTES DAS FUNÇÕES HTML PARA CISALHAMENTO")
    print("=" * 80)

    calc = CalculadoraCisalhamento()

    # -------------------------------------------------------------------------
    # TESTE 1: Seção adequada (Exemplo 2 do slide S10,dir)
    # -------------------------------------------------------------------------
    print("\n[TESTE 1] Seção com biela OK e armadura calculada > mínima")

    acoes_ok = AcoesCisalhamento(
        Vg_k=414.0, Vs_perm_k=195.8, Vq1_k=839.0,
        Vq2_k=0.0, Vt_k=0.0, psi_0=0.6, gamma_g=1.35, gamma_q=1.50
    )
    vsd_ok = calc.calcular_Vsd_combinacao(acoes_ok)

    res_ok = calc.dimensionar_modelo_I(
        Vsd=vsd_ok,
        bw=60.0,
        d=155.0,
        fck=30.0,
        fyk=500.0,
        alpha_estribo_graus=90.0,
        acoes=acoes_ok,
    )

    html_biela_ok = gerar_html_verificacao_biela(res_ok)
    html_resumo_ok = gerar_html_resumo_dimensionamento(res_ok)

    # Salva em arquivos separados
    with open("teste_ok_biela.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html_biela_ok}</body></html>")
    with open("teste_ok_resumo.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html_resumo_ok}</body></html>")
    print("  → Arquivos 'teste_ok_biela.html' e 'teste_ok_resumo.html' gerados.")

    assert "APROVADO" in html_biela_ok
    assert abs(res_ok.asw_calc_cm2_m - 21.0) < 0.5
    assert res_ok.Vc > 800.0
    assert not res_ok.esmagamento_biela
    print("  ✓ Verificações numéricas passaram.")

    # -------------------------------------------------------------------------
    # TESTE 2: Seção com esmagamento da biela (forçado)
    # -------------------------------------------------------------------------
    print("\n[TESTE 2] Seção com esmagamento da biela")

    res_falha = calc.dimensionar_modelo_I(
        Vsd=2500.0,
        bw=30.0,
        d=80.0,
        fck=20.0,
        fyk=500.0,
    )

    html_biela_falha = gerar_html_verificacao_biela(res_falha)
    html_resumo_falha = gerar_html_resumo_dimensionamento(res_falha)

    with open("teste_falha_biela.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html_biela_falha}</body></html>")
    with open("teste_falha_resumo.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html_resumo_falha}</body></html>")
    print("  → Arquivos 'teste_falha_biela.html' e 'teste_falha_resumo.html' gerados.")

    assert "REPROVADO" in html_biela_falha
    assert res_falha.esmagamento_biela is True
    assert res_falha.Vsd > res_falha.VRd2
    print("  ✓ Verificações de falha passaram.")

    # -------------------------------------------------------------------------
    # TESTE 3: Situação em que Vc ≥ Vsd (apenas armadura mínima)
    # -------------------------------------------------------------------------
    print("\n[TESTE 3] Concreto absorve todo o cisalhamento (Vsw = 0)")

    res_min = calc.dimensionar_modelo_I(
        Vsd=200.0,
        bw=80.0,
        d=200.0,
        fck=30.0,
        fyk=500.0,
    )

    html_biela_min = gerar_html_verificacao_biela(res_min)
    html_resumo_min = gerar_html_resumo_dimensionamento(res_min)

    with open("teste_minimo_biela.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html_biela_min}</body></html>")
    with open("teste_minimo_resumo.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html_resumo_min}</body></html>")
    print("  → Arquivos 'teste_minimo_biela.html' e 'teste_minimo_resumo.html' gerados.")

    assert res_min.Vsw < 1e-6
    assert res_min.asw_adotar_cm2_m == res_min.asw_min_cm2_m
    assert any("INFO" in al for al in res_min.alertas)
    print("  ✓ Verificações de armadura mínima passaram.")

    # -------------------------------------------------------------------------
    # TESTE 4: Estribos inclinados (α = 60°)
    # -------------------------------------------------------------------------
    print("\n[TESTE 4] Estribos inclinados a 60°")

    res_inc = calc.dimensionar_modelo_I(
        Vsd=1500.0,
        bw=50.0,
        d=120.0,
        fck=30.0,
        fyk=500.0,
        alpha_estribo_graus=60.0,
    )

    html_biela_inc = gerar_html_verificacao_biela(res_inc)
    html_resumo_inc = gerar_html_resumo_dimensionamento(res_inc)

    with open("teste_inclinado_biela.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html_biela_inc}</body></html>")
    with open("teste_inclinado_resumo.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html_resumo_inc}</body></html>")
    print("  → Arquivos 'teste_inclinado_biela.html' e 'teste_inclinado_resumo.html' gerados.")

    assert res_inc.alpha_graus == 60.0
    assert res_inc.asw_calc_cm2_m > 0
    print("  ✓ Inclinação registrada corretamente.")

    print("\n" + "=" * 80)
    print("✅ Todos os testes executados com sucesso.")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # TESTE 5: Cenário típico (espaçamento normal)
    # -------------------------------------------------------------------------
    print("\n[TESTE 5] Espaçamento normal, dentro do limite")
    asw_nec = 21.0      # cm²/m
    d_teste = 155.0     # cm
    diam = 8.0          # mm
    n_ramos = 2

    s1, html1 = gerar_html_espacamento_estribos(asw_nec, d_teste, diam, n_ramos)
    with open("teste_espacamento_normal.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html1}</body></html>")
    print(f"  → Espaçamento = {s1:.2f} cm (esperado ≈ 4.5 cm)")

    # Verificações numéricas
    area_1 = math.pi * (0.8 ** 2) / 4.0
    area_est = 2 * area_1
    s_calc_esperado = (area_est / asw_nec) * 100
    s_esperado = math.floor(s_calc_esperado * 2) / 2.0
    assert abs(s1 - s_esperado) < 0.01, "Erro no cálculo do espaçamento"
    assert "excede o limite máximo" not in html1
    print("  ✓ Cálculo correto e sem alerta.")

    # -------------------------------------------------------------------------
    # TESTE 62: Cenário com espaçamento excedendo o máximo
    # -------------------------------------------------------------------------
    print("\n[TESTE 6] Espaçamento excedendo o máximo normativo")
    # Asw pequena + d pequeno → s_max baixo, forçando exceder
    asw_nec2 = 2.5      # cm²/m
    d_teste2 = 40.0     # cm
    diam2 = 10.0        # mm
    n_ramos2 = 2

    s2, html2 = gerar_html_espacamento_estribos(asw_nec2, d_teste2, diam2, n_ramos2)
    with open("teste_espacamento_excedido.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html2}</body></html>")
    print(f"  → Espaçamento retornado = {s2:.2f} cm (limitado ao máximo)")

    # Verificações
    s_max = min(0.6 * d_teste2, 30.0)
    area_1_2 = math.pi * (1.0 ** 2) / 4.0
    area_est_2 = 2 * area_1_2
    s_calc_2 = (area_est_2 / asw_nec2) * 100
    s_final_2 = math.floor(s_calc_2 * 2) / 2.0
    assert s_final_2 > s_max, "Deveria exceder o máximo"
    assert s2 == s_max, "Espaçamento retornado deveria ser limitado ao máximo"
    assert "excede o limite máximo" in html2
    assert "⚠️ ATENÇÃO" in html2
    print("  ✓ Alerta exibido e espaçamento limitado corretamente.")

    # -------------------------------------------------------------------------
    # TESTE 7: Cenário com armadura zero (deve retornar infinito, mas tratado)
    # -------------------------------------------------------------------------
    print("\n[TESTE 7] Asw necessário zero (não usual, mas testa robustez)")
    s3, html3 = gerar_html_espacamento_estribos(0.0, 100.0, 8.0, 2)
    with open("teste_espacamento_zero.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html3}</body></html>")
    # Espaçamento infinito, mas a função limita ao máximo normativo
    s_max3 = min(0.6 * 100.0, 30.0)
    assert s3 == s_max3
    print(f"  → Espaçamento limitado ao máximo = {s3:.2f} cm")

    # -------------------------------------------------------------------------
    # TESTE 8: Diferentes números de ramos
    # -------------------------------------------------------------------------
    print("\n[TESTE 8] Estribo de 1 ramo (n_ramos = 1)")
    s4, html4 = gerar_html_espacamento_estribos(10.0, 120.0, 6.3, n_ramos=1)
    with open("teste_espacamento_1ramo.html", "w", encoding="utf-8") as f:
        f.write(f"<html><body style='background:#1e1e2e; padding:20px;'>{html4}</body></html>")
    print(f"  → Espaçamento = {s4:.2f} cm")
    assert s4 > 0
    assert "Número de ramos" in html4 and "1" in html4
    print("  ✓ Funcionamento com 1 ramo validado.")

    print("\n" + "=" * 80)
    print("✅ Todos os testes de espaçamento de estribos concluídos com sucesso.")
    print("=" * 80)

    # Testes AMPLITUDE DE TENSÃO ADMISSÍVEL PARA ESTRIBOS
    # Exemplo 1: Estribo ϕ16 mm sem informar pino (caso mais comum)
    delta1, html1 = calcular_delta_fad_estribo(16.0)
    print("Δf =", delta1, "MPa")
    # Para visualizar o HTML, salve em arquivo ou use em um notebook

    # Exemplo 2: Estribo ϕ16 mm com pino D = 80 mm (razão 5.0)
    delta2, html2 = calcular_delta_fad_estribo(16.0, diametro_pino_mm=80.0)
    print("Δf =", delta2, "MPa")

    # Exemplo 3: Condição soldada
    delta3, html3 = calcular_delta_fad_estribo(16.0, condicao='soldada')
    print("Δf =", delta3, "MPa")

"""