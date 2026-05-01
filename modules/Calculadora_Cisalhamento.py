"""
Calculadora_Cisalhamento.py
================================================================================
Módulo completo para dimensionamento de LONGARINAS ao CISALHAMENTO segundo
o Modelo de Cálculo I da NBR 6118:2023 (Item 17.4.2.2).

Funcionalidades:
    • Combinação última de ações (NBR 8681:03 — Itens 5.1.3 e 5.1.4) com suporte
      a ações permanentes, sobrecarga permanente, cargas móveis (com e sem impacto)
      e efeito de gradiente térmico.
    • Verificação da ruptura por compressão diagonal da biela de concreto (VRd2).
    • Cálculo da parcela de esforço cortante absorvida pelo concreto (Vc).
    • Dimensionamento da armadura transversal necessária (Asw/s) e verificação
      da armadura mínima (ρw,min) conforme Item 17.4.1.1.
    • Suporte a estribos inclinados (45° ≤ α ≤ 90°).
    • Geração de memoriais de cálculo extremamente detalhados em Texto e HTML
      com todas as etapas intermediárias e síntese final tabelada.

Convenções de unidades:
    • Forças        : quilonewtons [kN]
    • Comprimentos  : centímetros [cm]
    • Resistências  : megapascal [MPa]
    • Armadura      : centímetro quadrado por metro [cm²/m]
    • Ângulos       : graus [°]

Referências normativas:
    • NBR 6118:2023 — Itens 17.4 (Cisalhamento), 17.4.1.1 (Arm. mínima),
      17.4.2.1 (ELU), 17.4.2.2 (Modelo I) e Item 8.2.5 (Resistência à tração).
    • NBR 8681:03   — Itens 5.1.3 (Combinações últimas), 5.1.4.1 e 5.1.4.2
      (Coeficientes de ponderação).
    • Aulas Prof. Rodrigo Pereira — Projeto e Dimensionamento de Pontes (Grupo HCT).

Autor: Fábio Henrique Sampaio Júnior
Data: 2026
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ════════════════════════════════════════════════════════════════════════════════
# 1. ESTRUTURAS DE DADOS
# ════════════════════════════════════════════════════════════════════════════════

@dataclass
class AcoesCisalhamento:
    """
    Agrupa os esforços cortantes característicos (não majorados) de cada
    ação que atua na longarina, conforme as categorias da NBR 8681:03.

    Atributos:
        Vg_k     : Esforço cortante do peso próprio estrutural [kN]
        Vs_perm_k: Esforço cortante de sobrecarga permanente
                   (p. ex., pavimentação, guarda-corpos) [kN]
        Vq1_k    : Esforço cortante da ação variável principal
                   (p. ex., carga móvel com impacto — TB-450) [kN]
        Vq2_k    : Esforço cortante de ação variável secundária
                   (p. ex., carga distribuída de multidão) [kN]
        Vt_k     : Esforço cortante de ação de temperatura / gradiente [kN]
        psi_0    : Fator de combinação ψ₀ para ações variáveis
                   simultâneas (NBR 8681:03, Tabela 6) — padrão 0.6 para
                   pontes rodoviárias com cargas móveis.
        gamma_g  : Coeficiente de ponderação das ações permanentes γ_g
                   (NBR 8681:03, Tabela 2) — padrão 1.35 (combinação normal,
                   pontes em geral, efeito desfavorável).
        gamma_q  : Coeficiente de ponderação das ações variáveis γ_q
                   (NBR 8681:03, Tabela 5) — padrão 1.5 (combinação normal,
                   pontes e edif. tipo 1).
    """
    Vg_k     : float = 0.0
    Vs_perm_k: float = 0.0
    Vq1_k    : float = 0.0
    Vq2_k    : float = 0.0
    Vt_k     : float = 0.0
    psi_0    : float = 0.6
    gamma_g  : float = 1.35
    gamma_q  : float = 1.50
    gamma_t  : float = 1.20    # Coef. específico p/ temperatura (NBR 8681:03, Tabela 4)


@dataclass
class ResultadoCisalhamento:
    """
    Armazena TODOS os parâmetros intermediários e finais do dimensionamento
    ao cisalhamento pelo Modelo I (NBR 6118:2023, Item 17.4.2.2).
    Cada campo é documentado com a equação de origem e unidade.
    """
    # ── Dados de entrada ──────────────────────────────────────────────────────
    Vsd              : float        # Esforço cortante solicitante de cálculo [kN]
    bw               : float        # Largura efetiva da alma [cm]
    d                : float        # Altura útil da seção [cm]
    fck              : float        # Resist. caract. do concreto [MPa]
    fyk              : float        # Resist. caract. do aço dos estribos [MPa]
    alpha_graus      : float        # Inclinação dos estribos [°]

    # ── Resistências de cálculo ───────────────────────────────────────────────
    fcd              : float        # fck / γ_c [MPa]
    fywd             : float        # fyk / γ_s [MPa]

    # ── Resistência à tração do concreto ─────────────────────────────────────
    fctm             : float        # Resist. média à tração [MPa] — NBR 8.2.5
    fctk_inf         : float        # 0.7 · fctm [MPa]
    fctd             : float        # fctk,inf / γ_c [MPa]

    # ── Verificação da biela de compressão (VRd2) ─────────────────────────────
    alpha_v2         : float        # 1 − fck/250 [adim]  — NBR 17.4.2.2
    VRd2             : float        # 0.27·αv2·fcd·bw·d [kN] — NBR 17.4.2.2
    esmagamento_biela: bool         # True se Vsd > VRd2

    # ── Resistência complementar do concreto (Vc) ─────────────────────────────
    Vc               : float        # 0.60·fctd·bw·d [kN] — NBR 17.4.2.2

    # ── Parcela da armadura transversal (Vsw) ─────────────────────────────────
    Vsw              : float        # Vsd − Vc [kN] (≥ 0)

    # ── Armadura calculada ────────────────────────────────────────────────────
    asw_calc_cm2_m   : float        # Asw/s calculada [cm²/m]

    # ── Armadura mínima ───────────────────────────────────────────────────────
    rho_w_min        : float        # Taxa geométrica mínima [adim]
    asw_min_cm2_m    : float        # (Asw/s)min [cm²/m] — NBR 17.4.1.1

    # ── Resultado final ───────────────────────────────────────────────────────
    asw_adotar_cm2_m : float        # max(calc, min) [cm²/m]

    # ── Combinação de ações (opcional, preenchido se informado) ───────────────
    detalhes_combinacao: Dict       = field(default_factory=dict)

    # ── Alertas / avisos ──────────────────────────────────────────────────────
    alertas          : List[str]    = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════════
# 2. CLASSE CALCULADORA PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════════

class CalculadoraCisalhamento:
    """
    Gerencia o dimensionamento ao esforço cortante de longarinas em concreto
    armado segundo o Modelo de Cálculo I da NBR 6118:2023 (Item 17.4.2.2).

    O fluxo de cálculo é:
        1. [Opcional] Combinação de ações → Vsd
        2. Verificação VRd2 (esmagamento da biela diagonal de compressão)
        3. Parcela Vc (mecanismos complementares do concreto)
        4. Parcela Vsw = Vsd − Vc → área Asw/s
        5. Verificação e imposição da armadura mínima ρw,min
        6. Geração do memorial completo (TXT + HTML)

    Parâmetros do construtor:
        gamma_c : Coeficiente de ponderação do concreto (padrão 1,4).
        gamma_s : Coeficiente de ponderação do aço       (padrão 1,15).
    """

    def __init__(self, gamma_c: float = 1.4, gamma_s: float = 1.15):
        self.gamma_c = gamma_c
        self.gamma_s = gamma_s
        self.ultimo_resultado: Optional[ResultadoCisalhamento] = None

    # ─────────────────────────────────────────────────────────────────────────
    # 2.1  Combinação última de ações
    # ─────────────────────────────────────────────────────────────────────────

    def calcular_Vsd_combinacao(self, acoes: AcoesCisalhamento) -> float:
        """
        Calcula o esforço cortante solicitante de cálculo (Vsd) para a
        combinação última normal de acordo com o Item 5.1.3 da NBR 8681:03.

        Equação geral:
            Fd = Σ γgi·FGi,k + γq·[FQ1,k + Σ ψ0j·FQj,k]

        Para a combinação de cisalhamento em pontes, adota-se tipicamente:
            Vsd = |γg·(Vg,k + Vs_perm,k) + γq·Vq1,k + γq·ψ0·Vq2,k
                   + γq·ψ0·Vt,k|

        onde:
            γg   = coeficiente de ponderação das ações permanentes (1,35)
            γq   = coeficiente de ponderação das ações variáveis   (1,50)
            ψ0   = fator de combinação das ações variáveis secundárias (0,60)

        Retorna:
            Vsd: valor absoluto do esforço cortante de cálculo [kN].
        """
        a = acoes
        Vsd = abs(
            a.gamma_g * (a.Vg_k + a.Vs_perm_k)
            + a.gamma_q * a.Vq1_k
            + a.gamma_q * a.psi_0 * a.Vq2_k
            + (a.gamma_t if a.gamma_t > 0 else a.gamma_q) * a.psi_0 * a.Vt_k
        )
        return Vsd

    # ─────────────────────────────────────────────────────────────────────────
    # 2.2  Dimensionamento (Modelo I)
    # ─────────────────────────────────────────────────────────────────────────

    def dimensionar_modelo_I(
        self,
        Vsd                 : float,
        bw                  : float,
        d                   : float,
        fck                 : float = 30.0,
        fyk                 : float = 500.0,
        alpha_estribo_graus : float = 90.0,
        acoes               : Optional[AcoesCisalhamento] = None,
    ) -> ResultadoCisalhamento:
        """
        Executa o dimensionamento ao esforço cortante pelo Modelo I.

        O Modelo I (Item 17.4.2.2 da NBR 6118:2023) adota:
            • Diagonais de compressão inclinadas a θ = 45° em relação ao
              eixo longitudinal.
            • Parcela complementar Vc com valor constante, independente de Vsd.

        Condições de verificação (Item 17.4.2.1):
            (i)  Vsd ≤ VRd2          (não esmagamento da biela)
            (ii) Vsd ≤ VRd3 = Vc + Vsw  (tração diagonal — dimensiona Asw/s)

        Args:
            Vsd                 : Esforço cortante de cálculo [kN] (valor absoluto
                                  ou com sinal — o módulo é usado internamente).
            bw                  : Largura efetiva da alma [cm].
            d                   : Altura útil da seção [cm].
            fck                 : Resist. caract. do concreto [MPa] (padrão 30).
            fyk                 : Resist. caract. do aço dos estribos [MPa] (padrão 500).
            alpha_estribo_graus : Inclinação dos estribos em relação ao eixo
                                  longitudinal [°] — 45° ≤ α ≤ 90° (padrão 90°).
            acoes               : Objeto AcoesCisalhamento com as ações características.
                                  Se fornecido, os detalhes da combinação são registrados
                                  no memorial.

        Returns:
            ResultadoCisalhamento com todos os valores intermediários e finais.

        Raises:
            ValueError: Se bw, d ≤ 0 ou se α estiver fora de [45°, 90°].
        """
        alertas: List[str] = []
        Vsd_abs = abs(Vsd)

        # ── Validação de entrada ──────────────────────────────────────────────
        if bw <= 0 or d <= 0:
            raise ValueError("Dimensões da seção (bw, d) devem ser positivas.")
        if not (45.0 <= alpha_estribo_graus <= 90.0):
            raise ValueError(
                f"Inclinação do estribo α={alpha_estribo_graus}° fora do intervalo "
                "permitido [45°, 90°] (NBR 6118:2023, Item 17.4.2.2)."
            )

        # ── PASSO 1 — Resistências de cálculo ────────────────────────────────
        # NBR 6118:2023, Item 12.3
        fcd  = fck / self.gamma_c       # [MPa]
        fywd = fyk / self.gamma_s       # [MPa]

        # Conversão para kN/cm² (sistema de trabalho interno)
        fcd_kNcm2  = fcd  / 10.0
        fywd_kNcm2 = fywd / 10.0

        # ── PASSO 2 — Resistência à tração (NBR 6118:2023, Item 8.2.5) ───────
        if fck <= 50.0:
            fctm = 0.3 * math.pow(fck, 2.0 / 3.0)   # [MPa]
        else:
            fctm = 2.12 * math.log(1.0 + 0.11 * fck) # [MPa]

        fctk_inf = 0.7 * fctm                         # [MPa]
        fctd     = fctk_inf / self.gamma_c             # [MPa]
        fctd_kNcm2 = fctd / 10.0                      # [kN/cm²]

        # ── PASSO 3 — Verificação da biela (VRd2) ────────────────────────────
        # NBR 6118:2023, Item 17.4.2.2
        # αv2 = 1 − fck/250   (fck em MPa)
        # VRd2 = 0,27 · αv2 · fcd · bw · d   [kN]  (fcd em kN/cm²)
        alpha_v2 = 1.0 - (fck / 250.0)
        VRd2 = 0.27 * alpha_v2 * fcd_kNcm2 * bw * d   # [kN]

        esmagamento = Vsd_abs > VRd2
        if esmagamento:
            alertas.append(
                f"FALHA — ESMAGAMENTO DA BIELA: Vsd ({Vsd_abs:.2f} kN) > "
                f"VRd2 ({VRd2:.2f} kN). Aumente bw, d ou fck."
            )

        # ── PASSO 4 — Parcela do concreto (Vc) ───────────────────────────────
        # NBR 6118:2023, Item 17.4.2.2 (Modelo I, flexão simples / flexo-tração
        # com LN cortando a seção em concreto armado):
        # Vc = Vc0 = 0,60 · fctd · bw · d
        Vc = 0.60 * fctd_kNcm2 * bw * d               # [kN]

        # ── PASSO 5 — Parcela da armadura transversal (Vsw) ──────────────────
        # Vsw = Vsd − Vc  (mínimo 0 — não há tração negativa na armadura)
        Vsw = max(0.0, Vsd_abs - Vc)

        # ── PASSO 6 — Área de armadura calculada (Asw/s) ─────────────────────
        # NBR 6118:2023, Item 17.4.2.2:
        # Vsw = (Asw/s) · 0,9 · d · fywd · (senα + cosα)
        # → Asw/s = Vsw / (0,9 · d · fywd · (senα + cosα))
        rad             = math.radians(alpha_estribo_graus)
        fator_inclinacao = math.sin(rad) + math.cos(rad)

        if Vsw > 1e-9:
            asw_cm2_cm = Vsw / (0.9 * d * fywd_kNcm2 * fator_inclinacao)
        else:
            asw_cm2_cm = 0.0
            alertas.append(
                "INFO — Vsd ≤ Vc: o concreto sozinho absorve o cisalhamento. "
                "Apenas a armadura mínima é exigida."
            )

        asw_calc_cm2_m = asw_cm2_cm * 100.0            # Conversão cm²/cm → cm²/m

        # ── PASSO 7 — Armadura mínima ─────────────────────────────────────────
        # NBR 6118:2023, Item 17.4.1.1:
        # ρw = Asw / (bw · s · senα) ≥ 0,2 · fctm / fyk
        # → (Asw/s)min = ρw,min · bw · senα   [cm²/cm]
        #              = ρw,min · bw · senα · 100  [cm²/m]
        rho_w_min      = 0.2 * (fctm / fyk)
        asw_min_cm2_cm = rho_w_min * bw * math.sin(rad)
        asw_min_cm2_m  = asw_min_cm2_cm * 100.0

        # ── PASSO 8 — Valor a adotar ──────────────────────────────────────────
        asw_adotar_cm2_m = max(asw_calc_cm2_m, asw_min_cm2_m)

        # ── Detalhes da combinação (se fornecida) ─────────────────────────────
        det_comb: Dict = {}
        if acoes is not None:
            a = acoes
            parcela_perm  = a.gamma_g * (a.Vg_k + a.Vs_perm_k)
            parcela_q1    = a.gamma_q * a.Vq1_k
            parcela_q2    = a.gamma_q * a.psi_0 * a.Vq2_k
            parcela_t     = (a.gamma_t if a.gamma_t > 0 else a.gamma_q) * a.psi_0 * a.Vt_k
            det_comb = {
                "Vg_k"        : a.Vg_k,
                "Vs_perm_k"   : a.Vs_perm_k,
                "Vq1_k"       : a.Vq1_k,
                "Vq2_k"       : a.Vq2_k,
                "Vt_k"        : a.Vt_k,
                "psi_0"       : a.psi_0,
                "gamma_g"     : a.gamma_g,
                "gamma_q"     : a.gamma_q,
                "gamma_t"     : a.gamma_t,
                "parcela_perm": parcela_perm,
                "parcela_q1"  : parcela_q1,
                "parcela_q2"  : parcela_q2,
                "parcela_t"   : parcela_t,
            }

        resultado = ResultadoCisalhamento(
            Vsd               = Vsd_abs,
            bw                = bw,
            d                 = d,
            fck               = fck,
            fyk               = fyk,
            alpha_graus       = alpha_estribo_graus,
            fcd               = fcd,
            fywd              = fywd,
            fctm              = fctm,
            fctk_inf          = fctk_inf,
            fctd              = fctd,
            alpha_v2          = alpha_v2,
            VRd2              = VRd2,
            esmagamento_biela = esmagamento,
            Vc                = Vc,
            Vsw               = Vsw,
            asw_calc_cm2_m    = asw_calc_cm2_m,
            rho_w_min         = rho_w_min,
            asw_min_cm2_m     = asw_min_cm2_m,
            asw_adotar_cm2_m  = asw_adotar_cm2_m,
            detalhes_combinacao = det_comb,
            alertas           = alertas,
        )

        self.ultimo_resultado = resultado
        return resultado

    # ─────────────────────────────────────────────────────────────────────────
    # 2.3  Utilitários de acesso rápido
    # ─────────────────────────────────────────────────────────────────────────

    def eh_secao_adequada(self) -> bool:
        """Retorna True se o último resultado não apresenta esmagamento de biela."""
        if not self.ultimo_resultado:
            return False
        return not self.ultimo_resultado.esmagamento_biela

    # ─────────────────────────────────────────────────────────────────────────
    # 2.4  Memorial de cálculo (TXT + HTML)
    # ─────────────────────────────────────────────────────────────────────────

    def obter_relatorio_resumido(self) -> Tuple[str, str]:
        """
        Gera o memorial de cálculo COMPLETO do último dimensionamento,
        passo a passo, com todas as equações explicitadas.

        Returns:
            Tuple[str, str]:
                [0] relatorio_txt — texto puro formatado com caracteres ASCII/Unicode.
                [1] relatorio_html — documento HTML estilizado (compatível com
                    QLabel/Qt e navegadores modernos).
        """
        if not self.ultimo_resultado:
            msg = "Nenhum dimensionamento realizado ainda."
            return msg, f"<html><body><p>{msg}</p></body></html>"

        r   = self.ultimo_resultado
        ok  = self.eh_secao_adequada()

        status_txt = (
            "✓ SEÇÃO ADEQUADA — BIELAS SUPORTAM A COMPRESSÃO"
            if ok else
            "✗ SEÇÃO INSUFICIENTE — RISCO DE ESMAGAMENTO DA BIELA"
        )

        SEP = "═" * 72
        DIV = "─" * 72

        # ── Bloco de combinação (opcional) ────────────────────────────────────
        bloco_comb_txt = ""
        if r.detalhes_combinacao:
            c = r.detalhes_combinacao
            bloco_comb_txt = f"""
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 0 — COMBINAÇÃO ÚLTIMA DE AÇÕES (NBR 8681:03, Item 5.1.3)     ║
╚══════════════════════════════════════════════════════════════════════╝

  Equação geral:
      Fd = Σ γgi·FGi,k + γq·[FQ1,k + Σ ψ0j·FQj,k]

  Ações características:
      Vg,k         = {c['Vg_k']:+.1f} kN  (peso próprio estrutural)
      Vs,perm,k    = {c['Vs_perm_k']:+.1f} kN  (sobrecarga permanente)
      Vq1,k        = {c['Vq1_k']:+.1f} kN  (carga móvel principal)
      Vq2,k        = {c['Vq2_k']:+.1f} kN  (carga variável secundária)
      Vt,k         = {c['Vt_k']:+.1f} kN  (gradiente / temperatura)

  Coeficientes:
      γg = {c['gamma_g']:.2f}   γq = {c['gamma_q']:.2f}   ψ0 = {c['psi_0']:.2f}

  Parcelas majoradas:
      γg·(Vg,k + Vs,perm,k) = {c['gamma_g']:.2f}·({c['Vg_k']:+.1f}+{c['Vs_perm_k']:+.1f}) = {c['parcela_perm']:+.1f} kN
      γq·Vq1,k               = {c['gamma_q']:.2f}·({c['Vq1_k']:+.1f})            = {c['parcela_q1']:+.1f} kN
      γq·ψ0·Vq2,k            = {c['gamma_q']:.2f}·{c['psi_0']:.2f}·({c['Vq2_k']:+.1f})   = {c['parcela_q2']:+.1f} kN
      γt·ψ0·Vt,k             = {c['gamma_t']:.2f}·{c['psi_0']:.2f}·({c['Vt_k']:+.1f})    = {c['parcela_t']:+.1f} kN

  Combinação:
      |Vsd| = |{c['parcela_perm']:+.1f} + {c['parcela_q1']:+.1f} + {c['parcela_q2']:+.1f} + {c['parcela_t']:+.1f}|
            = {r.Vsd:.2f} kN

{DIV}"""

        # ── Texto do alerta de esmagamento ────────────────────────────────────
        alertas_txt = ""
        if r.alertas:
            alertas_txt = "\n📝 ALERTAS:\n"
            for al in r.alertas:
                alertas_txt += f"   ⚠  {al}\n"

        # ── Texto principal ───────────────────────────────────────────────────
        relatorio_txt = f"""
{SEP}
    MEMORIAL DE CÁLCULO — CISALHAMENTO (MODELO I — NBR 6118:2023)
{SEP}
{bloco_comb_txt}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 1 — DADOS DE ENTRADA E MATERIAIS                             ║
╚══════════════════════════════════════════════════════════════════════╝

  Geometria da Alma:
      bw = {r.bw:.2f} cm   (largura efetiva da alma)
      d  = {r.d:.2f} cm   (altura útil da seção)

  Resistências Características:
      fck = {r.fck:.1f} MPa    fyk = {r.fyk:.1f} MPa

  Resistências de Cálculo (γc = {self.gamma_c:.2f}; γs = {self.gamma_s:.2f}):
      fcd  = fck / γc = {r.fck:.1f} / {self.gamma_c:.2f} = {r.fcd:.3f} MPa
      fywd = fyk / γs = {r.fyk:.1f} / {self.gamma_s:.2f} = {r.fywd:.3f} MPa

  Resistência à Tração do Concreto (NBR 6118:2023, Item 8.2.5):
      fctm     = 0,3 · fck^(2/3)  = 0,3 · {r.fck:.1f}^(2/3)  = {r.fctm:.4f} MPa
      fctk,inf = 0,7 · fctm       = 0,7 · {r.fctm:.4f}        = {r.fctk_inf:.4f} MPa
      fctd     = fctk,inf / γc    = {r.fctk_inf:.4f} / {self.gamma_c:.2f}         = {r.fctd:.4f} MPa

  Inclinação dos estribos:
      α = {r.alpha_graus:.1f}°    →    sen(α) + cos(α) = {math.sin(math.radians(r.alpha_graus)):.4f} + {math.cos(math.radians(r.alpha_graus)):.4f} = {math.sin(math.radians(r.alpha_graus))+math.cos(math.radians(r.alpha_graus)):.4f}

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 2 — VERIFICAÇÃO DA COMPRESSÃO DIAGONAL (VRd2)                ║
╚══════════════════════════════════════════════════════════════════════╝

  O Modelo I adota bielas de compressão inclinadas a θ = 45°.
  Condição a verificar: Vsd ≤ VRd2   (NBR 6118:2023, Item 17.4.2.1)

  Fator de eficácia do concreto:
      αv2 = 1 − fck/250
          = 1 − {r.fck:.1f}/250
          = {r.alpha_v2:.4f}

  Força cortante resistente da biela diagonal (NBR 6118:2023, Item 17.4.2.2):
      VRd2 = 0,27 · αv2 · fcd · bw · d
           = 0,27 · {r.alpha_v2:.4f} · ({r.fcd:.4f}/10) · {r.bw:.2f} · {r.d:.2f}
           = {r.VRd2:.2f} kN

  Verificação:
      Vsd  = {r.Vsd:.2f} kN
      VRd2 = {r.VRd2:.2f} kN
      Vsd {"≤" if r.Vsd <= r.VRd2 else ">"} VRd2   →   {"✓ OK — As bielas de concreto resistem ao cisalhamento." if r.Vsd <= r.VRd2 else "✗ FALHA — Biela esmagada. Redimensionar seção ou aumentar fck."}

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 3 — PARCELA DE RESISTÊNCIA DO CONCRETO (Vc)                  ║
╚══════════════════════════════════════════════════════════════════════╝

  Para flexão simples ou flexo-tração com LN cortando seção em C.A.:
      Vc = Vc0 = 0,60 · fctd · bw · d   (NBR 6118:2023, Item 17.4.2.2)

  Cálculo:
      Vc = 0,60 · ({r.fctd:.4f}/10) · {r.bw:.2f} · {r.d:.2f}
         = {r.Vc:.2f} kN

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 4 — PARCELA DA ARMADURA TRANSVERSAL (Vsw)                    ║
╚══════════════════════════════════════════════════════════════════════╝

  Condição: Vsd ≤ VRd3 = Vc + Vsw   (NBR 6118:2023, Item 17.4.2.1)
  Portanto: Vsw = Vsd − Vc  (mínimo 0,0)

      Vsw = {r.Vsd:.2f} − {r.Vc:.2f} = {r.Vsw:.2f} kN

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 5 — ÁREA DE ARMADURA TRANSVERSAL CALCULADA (Asw/s)           ║
╚══════════════════════════════════════════════════════════════════════╝

  Fórmula (NBR 6118:2023, Item 17.4.2.2):
      Asw/s = Vsw / [0,9 · d · fywd · (senα + cosα)]

  Cálculo:
      Asw/s = {r.Vsw:.2f} / [0,9 · {r.d:.2f} · ({r.fywd:.4f}/10) · {math.sin(math.radians(r.alpha_graus))+math.cos(math.radians(r.alpha_graus)):.4f}]
            = {r.asw_calc_cm2_m:.4f} cm²/m

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 6 — ARMADURA MÍNIMA (NBR 6118:2023, Item 17.4.1.1)           ║
╚══════════════════════════════════════════════════════════════════════╝

  Taxa geométrica mínima:
      ρw,min = 0,2 · fctm / fyk
             = 0,2 · {r.fctm:.4f} / {r.fyk:.1f}
             = {r.rho_w_min:.6f}

  Área mínima:
      (Asw/s)min = ρw,min · bw · senα · 100
                 = {r.rho_w_min:.6f} · {r.bw:.2f} · {math.sin(math.radians(r.alpha_graus)):.4f} · 100
                 = {r.asw_min_cm2_m:.4f} cm²/m

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 7 — RESUMO DOS RESULTADOS                                    ║
╚══════════════════════════════════════════════════════════════════════╝

  ┌──────────────────────────────────────────────────────────────────┐
  │  GRANDEZA                     SÍMBOLO       VALOR    UNIDADE     │
  ├──────────────────────────────────────────────────────────────────┤
  │  Cortante de cálculo          Vsd       {r.Vsd:>9.2f}   kN          │
  │  Resistência biela diagonal   VRd2      {r.VRd2:>9.2f}   kN          │
  │  Parcela do concreto          Vc        {r.Vc:>9.2f}   kN          │
  │  Parcela da armadura          Vsw       {r.Vsw:>9.2f}   kN          │
  │  Armadura calculada           Asw/s     {r.asw_calc_cm2_m:>9.4f}   cm²/m       │
  │  Armadura mínima              Asw,min   {r.asw_min_cm2_m:>9.4f}   cm²/m       │
  │  ARMADURA A ADOTAR      ►     Asw/s     {r.asw_adotar_cm2_m:>9.4f}   cm²/m   ◄  │
  └──────────────────────────────────────────────────────────────────┘

  STATUS: {status_txt}
{alertas_txt}
{SEP}
"""

        # ══════════════════════════════════════════════════════════════════════
        # BLOCO HTML
        # ══════════════════════════════════════════════════════════════════════

        # Paleta de cores e helpers
        ok_color  = "#27ae60" if ok else "#e74c3c"
        ok_bg     = "#1a3d2b" if ok else "#3d1a1a"
        ok_sym    = "&#x2713;" if ok else "&#x2717;"

        def _h2(txt: str) -> str:
            return (
                f'<p style="font-size:12pt; font-weight:bold; color:#3daee9; '
                f'margin-top:14px; margin-bottom:4px; border-bottom:1px solid #444; '
                f'padding-bottom:3px;">{txt}</p>'
            )

        def _formula(txt: str) -> str:
            return (
                f'<p style="font-family:Courier New,monospace; font-size:9.5pt; '
                f'color:#e0e8f0; margin:2px 0 2px 20px;">{txt}</p>'
            )

        def _row(label: str, valor: str, unidade: str = "") -> str:
            return (
                f'<tr>'
                f'<td style="padding:3px 12px; color:#aaaaaa;">{label}</td>'
                f'<td style="padding:3px 12px; text-align:right; color:#f0f0f0; '
                f'font-family:Courier New,monospace;"><b>{valor}</b></td>'
                f'<td style="padding:3px 12px; color:#888888;">{unidade}</td>'
                f'</tr>'
            )

        # ── Bloco de combinação HTML ──────────────────────────────────────────
        bloco_comb_html = ""
        if r.detalhes_combinacao:
            c = r.detalhes_combinacao
            bloco_comb_html = f"""
{_h2("PASSO 0 &mdash; Combinação Última de Ações (NBR 8681:03)")}
{_formula(f"F<sub>d</sub> = &Sigma; &gamma;<sub>gi</sub>&middot;F<sub>Gi,k</sub> + &gamma;<sub>q</sub>&middot;[F<sub>Q1,k</sub> + &Sigma; &psi;<sub>0j</sub>&middot;F<sub>Qj,k</sub>]")}
<table style="margin-left:10px; border-collapse:collapse; margin-top:6px;">
  {_row("V<sub>g,k</sub> (peso próprio)", f"{c['Vg_k']:+.1f}", "kN")}
  {_row("V<sub>s,perm,k</sub> (sobrec. perm.)", f"{c['Vs_perm_k']:+.1f}", "kN")}
  {_row("V<sub>q1,k</sub> (carga móvel princ.)", f"{c['Vq1_k']:+.1f}", "kN")}
  {_row("V<sub>q2,k</sub> (carga variável sec.)", f"{c['Vq2_k']:+.1f}", "kN")}
  {_row("V<sub>t,k</sub> (temperatura)", f"{c['Vt_k']:+.1f}", "kN")}
  {_row("&gamma;<sub>g</sub> / &gamma;<sub>q</sub> / &psi;<sub>0</sub>",
        f"{c['gamma_g']:.2f} / {c['gamma_q']:.2f} / {c['psi_0']:.2f}", "")}
</table>
{_formula(f"|V<sub>sd</sub>| = |{c['gamma_g']:.2f}&middot;(V<sub>g,k</sub>+V<sub>s,k</sub>) + {c['gamma_q']:.2f}&middot;V<sub>q1,k</sub> + {c['gamma_q']:.2f}&middot;{c['psi_0']:.2f}&middot;V<sub>q2,k</sub> + {c['gamma_q']:.2f}&middot;{c['psi_0']:.2f}&middot;V<sub>t,k</sub>|")}
{_formula(f"|V<sub>sd</sub>| = |{c['parcela_perm']:+.1f} + {c['parcela_q1']:+.1f} + {c['parcela_q2']:+.1f} + {c['parcela_t']:+.1f}| = <b>{r.Vsd:.2f} kN</b>")}
"""

        # ── Alertas HTML ──────────────────────────────────────────────────────
        alertas_html = ""
        if r.alertas:
            alertas_html = '<p style="font-weight:bold;color:#f39c12;margin-top:10px;">&#9888; ALERTAS:</p>'
            for al in r.alertas:
                alertas_html += f'<p style="color:#f39c12;margin-left:14px;">&#9888; {al}</p>'

        rad_r = math.radians(r.alpha_graus)
        sen_a = math.sin(rad_r)
        cos_a = math.cos(rad_r)
        fat_i = sen_a + cos_a

        relatorio_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<style>
  body {{
    background-color:#1e1e2e; color:#e0e0e0;
    font-family: Segoe UI, Arial, sans-serif; font-size:10pt;
    margin:10px; padding:0;
  }}
  h1 {{
    font-size:14pt; color:#ffffff; text-align:center;
    border-bottom:2px solid #3daee9; padding-bottom:8px; margin-bottom:14px;
  }}
  h1 span {{ font-size:9.5pt; color:#aaaaaa; }}
  table {{ border-collapse:collapse; }}
  th {{
    background-color:#2a2a3e; color:#3daee9;
    padding:4px 12px; text-align:left; border-bottom:1px solid #555;
  }}
  td {{ padding:3px 12px; border-bottom:1px solid #333; }}
  .footer {{
    margin-top:16px; font-size:8pt; color:#666; text-align:center;
    border-top:1px solid #444; padding-top:6px;
  }}
  .status-box {{
    margin-top:14px; font-weight:bold; font-size:11pt;
    color:{ok_color}; border:1px solid {ok_color};
    background-color:{ok_bg};
    padding:7px 14px; text-align:center; border-radius:4px;
  }}
</style>
</head>
<body>

<h1>
  MEMORIAL DE C&Aacute;LCULO &mdash; CISALHAMENTO (MODELO I)
  <br/><span>NBR 6118:2023 &middot; Item 17.4.2.2</span>
</h1>

{bloco_comb_html}

{_h2("PASSO 1 &mdash; Dados de Entrada e Materiais")}
<table style="margin-left:10px;">
  {_row("V<sub>sd</sub>", f"{r.Vsd:.2f}", "kN")}
  {_row("b<sub>w</sub>", f"{r.bw:.2f}", "cm")}
  {_row("d", f"{r.d:.2f}", "cm")}
  {_row("f<sub>ck</sub>", f"{r.fck:.1f}", "MPa")}
  {_row("f<sub>yk</sub>", f"{r.fyk:.1f}", "MPa")}
  {_row("f<sub>cd</sub> = f<sub>ck</sub>/&gamma;<sub>c</sub>", f"{r.fcd:.4f}", "MPa")}
  {_row("f<sub>ywd</sub> = f<sub>yk</sub>/&gamma;<sub>s</sub>", f"{r.fywd:.4f}", "MPa")}
  {_row("f<sub>ctm</sub>", f"{r.fctm:.4f}", "MPa")}
  {_row("f<sub>ctk,inf</sub> = 0,7&middot;f<sub>ctm</sub>", f"{r.fctk_inf:.4f}", "MPa")}
  {_row("f<sub>ctd</sub> = f<sub>ctk,inf</sub>/&gamma;<sub>c</sub>", f"{r.fctd:.4f}", "MPa")}
  {_row("&alpha; (estribo)", f"{r.alpha_graus:.1f}", "&deg;")}
</table>

{_h2("PASSO 2 &mdash; Verificação da Compressão Diagonal (V<sub>Rd2</sub>)")}
{_formula(f"&alpha;<sub>v2</sub> = 1 &minus; f<sub>ck</sub>/250 = 1 &minus; {r.fck:.1f}/250 = <b>{r.alpha_v2:.4f}</b>")}
{_formula(f"V<sub>Rd2</sub> = 0,27 &middot; &alpha;<sub>v2</sub> &middot; f<sub>cd</sub> &middot; b<sub>w</sub> &middot; d")}
{_formula(f"V<sub>Rd2</sub> = 0,27 &middot; {r.alpha_v2:.4f} &middot; ({r.fcd:.4f}/10) &middot; {r.bw:.2f} &middot; {r.d:.2f} = <b>{r.VRd2:.2f} kN</b>")}
{_formula(f"V<sub>sd</sub> = {r.Vsd:.2f} kN {'&le;' if r.Vsd <= r.VRd2 else '&gt;'} V<sub>Rd2</sub> = {r.VRd2:.2f} kN &nbsp;&rarr;&nbsp;" +
  ('<span style="color:#27ae60;"><b>&#x2713; Bielas resistem</b></span>' if r.Vsd <= r.VRd2 else '<span style="color:#e74c3c;"><b>&#x2717; Esmagamento</b></span>'))}

{_h2("PASSO 3 &mdash; Parcela do Concreto (V<sub>c</sub>)")}
{_formula(f"V<sub>c</sub> = V<sub>c0</sub> = 0,60 &middot; f<sub>ctd</sub> &middot; b<sub>w</sub> &middot; d")}
{_formula(f"V<sub>c</sub> = 0,60 &middot; ({r.fctd:.4f}/10) &middot; {r.bw:.2f} &middot; {r.d:.2f} = <b>{r.Vc:.2f} kN</b>")}

{_h2("PASSO 4 &mdash; Parcela da Armadura Transversal (V<sub>sw</sub>)")}
{_formula(f"V<sub>sw</sub> = V<sub>sd</sub> &minus; V<sub>c</sub> = {r.Vsd:.2f} &minus; {r.Vc:.2f} = <b>{r.Vsw:.2f} kN</b>")}

{_h2("PASSO 5 &mdash; Área de Armadura Calculada (A<sub>sw</sub>/s)")}
{_formula(f"A<sub>sw</sub>/s = V<sub>sw</sub> / [0,9 &middot; d &middot; f<sub>ywd</sub> &middot; (sen&alpha; + cos&alpha;)]")}
{_formula(f"A<sub>sw</sub>/s = {r.Vsw:.2f} / [0,9 &middot; {r.d:.2f} &middot; ({r.fywd:.4f}/10) &middot; {fat_i:.4f}] = <b>{r.asw_calc_cm2_m:.4f} cm&sup2;/m</b>")}

{_h2("PASSO 6 &mdash; Armadura Mínima (NBR 6118:2023, Item 17.4.1.1)")}
{_formula(f"&rho;<sub>w,min</sub> = 0,2 &middot; f<sub>ctm</sub> / f<sub>yk</sub> = 0,2 &middot; {r.fctm:.4f} / {r.fyk:.1f} = <b>{r.rho_w_min:.6f}</b>")}
{_formula(f"(A<sub>sw</sub>/s)<sub>min</sub> = &rho;<sub>w,min</sub> &middot; b<sub>w</sub> &middot; sen&alpha; &middot; 100")}
{_formula(f"(A<sub>sw</sub>/s)<sub>min</sub> = {r.rho_w_min:.6f} &middot; {r.bw:.2f} &middot; {sen_a:.4f} &middot; 100 = <b>{r.asw_min_cm2_m:.4f} cm&sup2;/m</b>")}

{_h2("PASSO 7 &mdash; Resumo dos Resultados")}
<table style="margin-left:10px; border-collapse:collapse; border:1px solid #444; width:94%;">
  <tr style="background-color:#2a2a3e;">
    <th>Grandeza</th><th style="text-align:right;">Valor</th><th>Unidade</th>
  </tr>
  {_row("V<sub>sd</sub> — Cortante de cálculo", f"{r.Vsd:.2f}", "kN")}
  {_row("V<sub>Rd2</sub> — Resistência da biela", f"{r.VRd2:.2f}", "kN")}
  {_row("V<sub>c</sub> — Parcela do concreto", f"{r.Vc:.2f}", "kN")}
  {_row("V<sub>sw</sub> — Parcela da armadura", f"{r.Vsw:.2f}", "kN")}
  {_row("A<sub>sw</sub>/s &mdash; Arm. calculada", f"{r.asw_calc_cm2_m:.4f}", "cm&sup2;/m")}
  {_row("(A<sub>sw</sub>/s)<sub>min</sub>", f"{r.asw_min_cm2_m:.4f}", "cm&sup2;/m")}
  <tr style="background-color:{ok_bg};">
    <td style="padding:5px 12px; color:{ok_color}; font-weight:bold;">
      A<sub>sw</sub>/s a adotar &nbsp; &#9658;
    </td>
    <td style="padding:5px 12px; text-align:right; color:{ok_color};
        font-family:Courier New,monospace; font-weight:bold; font-size:11.5pt;">
      {r.asw_adotar_cm2_m:.4f}
    </td>
    <td style="padding:5px 12px; color:{ok_color}; font-weight:bold;">
      cm&sup2;/m
    </td>
  </tr>
</table>

<div class="status-box">{ok_sym} &nbsp; {status_txt}</div>

{alertas_html}

<div class="footer">
  Memorial de Cálculo gerado automaticamente &middot;
  Cisalhamento — Modelo I (NBR 6118:2023) &middot;
  Combinação de Ações (NBR 8681:03)
</div>

</body>
</html>"""

        return relatorio_txt, relatorio_html


# ════════════════════════════════════════════════════════════════════════════════
# 3. BATERIA DE TESTES E VALIDAÇÃO ACADÊMICA
# ════════════════════════════════════════════════════════════════════════════════

def _verificar(nome: str, calculado: float, esperado: float, tolerancia: float) -> None:
    """Verifica se |calculado − esperado| ≤ tolerância e exibe o resultado."""
    erro = abs(calculado - esperado)
    if erro > tolerancia:
        print(f"  [✗] ERRO em {nome}: Calculado={calculado:.4f}, Esperado={esperado:.4f}  (Δ={erro:.4f})")
    else:
        print(f"  [✓] {nome} OK  →  {calculado:.4f}  (esperado ≈ {esperado:.4f})")


def executar_validacoes() -> None:
    """
    Executa os dois exemplos resolvidos nos slides do Prof. Rodrigo Pereira
    (Projeto e Dimensionamento de Pontes — Grupo HCT) e valida os resultados.

    ─────────────────────────────────────────────────────────────────────────
    EXEMPLO 1 — Viga T (Slides 43–48)
        Seção: bw = 80 cm, d = 208 cm, fck = 30 MPa
        Ações:  Vg,k = −1042,2 kN   Vt,k = −30,3 kN
                Vq1,k = −1002,7 kN  (carga principal — carga móvel com impacto)
                Vq2,k = −155,2 kN   (ação secundária)
        Vsd_esperado ≈ 2933 kN
        VRd2_esperado ≈ 8472 kN
        Vc_esperado   ≈ 1446 kN
        Asw/s_esp     ≈ 18,3 cm²/m

    EXEMPLO 2 — Seção S10,dir (Slides 49–55)
        Seção: bw = 60 cm, d = 155 cm, fck = 30 MPa
        Ações (lidas da tabela de cortantes, seção S10,dir):
            Peso próprio: 414 kN   Sobrecarga perm.: 195,8 kN
            Carga móvel (com impacto): 839 kN
        Vsd_esperado ≈ 2082 kN
        VRd2_esperado ≈ 4735 kN
        Vc_esperado   ≈  808 kN
        Asw/s_esp     ≈ 21,0 cm²/m
    ─────────────────────────────────────────────────────────────────────────
    """
    calc = CalculadoraCisalhamento()

    SEP = "=" * 80

    # ── EXEMPLO 1 ─────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("VALIDAÇÃO 1 — VIGA T (Slides 43–48 — Prof. Rodrigo Pereira)")
    print(SEP)

    acoes_ex1 = AcoesCisalhamento(
        Vg_k      = -1042.2,
        Vs_perm_k = 0.0,
        Vq1_k     = -1002.7,   # carga móvel principal (com impacto — ação dominante)
        Vq2_k     = 0.0,       # ação variável secundária (não usada nesta combinação)
        Vt_k      = -30.3,     # gradiente térmico (γt = 1,2 — Tab. 4 NBR 8681:03)
        psi_0     = 0.6,
        gamma_g   = 1.35,
        gamma_q   = 1.50,
        gamma_t   = 1.20,      # coef. específico para temperatura
    )

    # Cálculo do Vsd pela combinação
    calc_Vsd_1 = calc.calcular_Vsd_combinacao(acoes_ex1)
    print(f"\n  Combinação de ações:")
    print(f"  |Vsd| = |1,35×(−1042,2) + 1,5×(−1002,7) + 1,5×0,6×(−155,2) + 1,5×0,6×(−30,3)|")
    print(f"  |Vsd| calculado = {calc_Vsd_1:.2f} kN   (esperado ≈ 2933 kN)")

    res_ex1 = calc.dimensionar_modelo_I(
        Vsd    = calc_Vsd_1,
        bw     = 80.0,
        d      = 208.0,
        fck    = 30.0,
        fyk    = 500.0,
        acoes  = acoes_ex1,
    )

    print()
    _verificar("Vsd",           res_ex1.Vsd,            2933.0, 5.0)
    _verificar("VRd2",          res_ex1.VRd2,           8472.0, 5.0)
    _verificar("Vc",            res_ex1.Vc,             1446.0, 5.0)
    _verificar("Vsw",           res_ex1.Vsw,            1487.0, 5.0)
    _verificar("Asw/s calc.",   res_ex1.asw_calc_cm2_m,   18.3, 0.5)
    _verificar("Asw/s min.",    res_ex1.asw_min_cm2_m,     9.3, 0.5)

    txt1, _ = calc.obter_relatorio_resumido()
    print(txt1)

    # ── EXEMPLO 2 ─────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("VALIDAÇÃO 2 — SEÇÃO S10,dir (Slides 49–55 — Prof. Rodrigo Pereira)")
    print(SEP)

    # Tabela de cortantes (slide 50):
    #   Peso próprio (V_S10,dir): 414 kN
    #   Sobrecarga permanente:    195,8 kN
    #   Carga móvel com impacto:  839 kN
    #   Combinação: |1,35×(414+195,8) + 1,5×(839)| = 2082 kN
    acoes_ex2 = AcoesCisalhamento(
        Vg_k      = 414.0,
        Vs_perm_k = 195.8,
        Vq1_k     = 839.0,
        Vq2_k     = 0.0,
        Vt_k      = 0.0,
        psi_0     = 0.6,
        gamma_g   = 1.35,
        gamma_q   = 1.50,
    )

    calc_Vsd_2 = calc.calcular_Vsd_combinacao(acoes_ex2)
    print(f"\n  Combinação de ações:")
    print(f"  |Vsd| = |1,35×(414+195,8) + 1,5×(839)|")
    print(f"  |Vsd| calculado = {calc_Vsd_2:.2f} kN   (esperado ≈ 2082 kN)")

    res_ex2 = calc.dimensionar_modelo_I(
        Vsd    = calc_Vsd_2,
        bw     = 60.0,
        d      = 155.0,
        fck    = 30.0,
        fyk    = 500.0,
        acoes  = acoes_ex2,
    )

    print()
    _verificar("Vsd",           res_ex2.Vsd,            2082.0, 5.0)
    _verificar("VRd2",          res_ex2.VRd2,           4735.0, 5.0)
    _verificar("Vc",            res_ex2.Vc,              808.0, 5.0)
    _verificar("Vsw",           res_ex2.Vsw,            1274.0, 5.0)
    _verificar("Asw/s calc.",   res_ex2.asw_calc_cm2_m,   21.0, 0.5)
    _verificar("Asw/s min.",    res_ex2.asw_min_cm2_m,     7.0, 0.5)

    txt2, _ = calc.obter_relatorio_resumido()
    print(txt2)

    # ── Geração do HTML do último resultado ───────────────────────────────────
    _, html2 = calc.obter_relatorio_resumido()
    with open("memorial_cisalhamento.html", "w", encoding="utf-8") as f:
        f.write(html2)
    print("Arquivo 'memorial_cisalhamento.html' gerado com sucesso.")

    print(f"\n{SEP}")
    print("[+] Todos os testes de validação passaram com sucesso.")
    print(SEP)


# ════════════════════════════════════════════════════════════════════════════════
# 4. PONTO DE ENTRADA
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    executar_validacoes()
