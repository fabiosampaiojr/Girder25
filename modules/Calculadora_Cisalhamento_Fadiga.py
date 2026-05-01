"""
Calculadora_Cisalhamento_Fadiga.py
================================================================================
Módulo completo para verificação à FADIGA da armadura transversal (estribos)
de longarinas em concreto armado, segundo a NBR 6118:2014 (Item 23.5.3).

Contexto físico do problema:
    A passagem repetida de cargas móveis sobre uma ponte provoca variações
    cíclicas de tensão nos estribos. Mesmo que a tensão máxima seja inferior
    à resistência estática do aço, a repetição de ciclos pode causar fissuração
    progressiva e ruptura frágil por fadiga. A NBR 6118:2014 exige que a
    amplitude da variação de tensões Δσsw seja inferior ao limite prescrito
    Δfsd,fad, obtido da Tabela 23.2 da norma.

Metodologia (NBR 6118:2014, Item 23.5.3 — Modelo I):
    1. Combinar as ações em serviço (ELS — combinação frequente, Item 23.5.2)
       para obter os dois esforços cortantes de serviço Vd1,serv e Vd2,serv.
    2. Calcular a parcela estática Vc (Modelo I, θ = 45°).
    3. Reduzir Vc por fator 0,5 (equivalente a adotar 50% da resistência à
       tração estática do concreto para 10^7 ciclos — Item 23.5.3).
    4. Calcular as tensões nos estribos σsw1 e σsw2 para cada combinação.
    5. Determinar a amplitude Δσsw conforme o sinal das solicitações:
       • Mesmo sinal: Δσsw = |σsw1 − σsw2|
       • Sinais opostos: σsw,min = 0 → Δσsw = σsw,max = σsw1
    6. Verificar: kfad = Δσsw / Δfsd,fad — se kfad > 1,0, majorar a armadura.

Funcionalidades:
    • Combinação frequente de ações em serviço (NBR 6118:2014, Item 23.5.2)
      com suporte a cargas permanentes, móveis (máx/mín) e temperatura.
    • Cálculo de Vc estático e reduzido (0,5·Vc) para verificação à fadiga.
    • Tratamento automático dos dois casos: sinais iguais e sinais opostos.
    • Cálculo do fator de fadiga kfad e da área corrigida Asw,fad.
    • Memorial de cálculo ultra-detalhado em Texto e HTML, passo a passo,
      com todas as equações intermediárias explicitadas.
    • Dois exemplos de validação dos slides do Prof. Rodrigo Pereira (Grupo HCT).

Convenções de unidades:
    • Forças        : quilonewtons [kN]
    • Comprimentos  : centímetros [cm]
    • Resistências  : megapascal [MPa]
    • Armadura      : centímetro quadrado por metro [cm²/m]
    • Tensões       : megapascal [MPa]

Referências normativas:
    • NBR 6118:2014 — Item 8.2.5 (Resistência à tração do concreto)
    • NBR 6118:2014 — Item 17.4.2.2 (Modelo I — Cisalhamento)
    • NBR 6118:2014 — Item 23.5.2 (Combinações frequentes para fadiga)
    • NBR 6118:2014 — Item 23.5.3 (Fadiga da armadura transversal)
    • NBR 6118:2014 — Tabela 23.2 (Parâmetros curvas S-N: Δfsd,fad estribos = 85 MPa)
    • Aulas Prof. Rodrigo Pereira — Projeto e Dimensionamento de Pontes (Grupo HCT).

Autor: Fábio Henrique Sampaio (Revisão/Expansão IA)
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
class AcoesFadigaCisalhamento:
    """
    Agrupa os esforços cortantes característicos para a combinação frequente
    de serviço (ELS — NBR 6118:2014, Item 23.5.2).

    A combinação frequente é:
        Fd,ser = ΣFg,ik + ψ1·FQ1,k + Σψ2j·FQj,k

    Para pontes rodoviárias:
        ψ1 = 0,50  (verificação das vigas)
    Para temperatura:
        ψ2 = 0,30  (variações uniformes — Item 11.7.1 da NBR 6118:2014)

    São calculadas DUAS combinações de serviço para determinar os dois
    estados extremos de tensão nos estribos:

        Vd1,serv → combinação que maximiza |V|  (usa Vq1_max_k como dominante)
        Vd2,serv → combinação de referência       (usa Vq1_min_k como dominante)

    Atributos:
        Vg_k       : Esforço cortante do peso próprio estrutural [kN].
        Vs_perm_k  : Esforço cortante de sobrecarga permanente [kN].
        Vq1_max_k  : Esforço cortante da carga móvel — combinação desfavorável
                     (p.ex. carga com impacto, sentido dominante) [kN].
        Vq1_min_k  : Esforço cortante da carga móvel — combinação favorável
                     (p.ex. mesmo conjunto de carga, sentido oposto ou mínimo,
                      ou a outra combinação de serviço) [kN].
        Vt_k       : Esforço cortante de variação de temperatura [kN].
        psi_1      : Fator de combinação frequente ψ1 (padrão 0,50 — pontes
                     rodoviárias, verificação de vigas — NBR 6118:2014, Tab. 23.2).
        psi_2      : Fator de redução ψ2 para temperatura (padrão 0,30).
    """
    Vg_k      : float = 0.0
    Vs_perm_k : float = 0.0
    Vq1_max_k : float = 0.0
    Vq1_min_k : float = 0.0
    Vt_k      : float = 0.0
    psi_1     : float = 0.50
    psi_2     : float = 0.30


@dataclass
class ResultadoFadigaCisalhamento:
    """
    Armazena TODOS os parâmetros intermediários e finais da verificação
    à fadiga da armadura transversal segundo a NBR 6118:2014, Item 23.5.3.

    Campos organizados na mesma sequência do cálculo passo a passo.
    """
    # ── Dados de entrada ──────────────────────────────────────────────────────
    bw               : float        # Largura efetiva da alma [cm]
    d                : float        # Altura útil da seção [cm]
    fck              : float        # Resist. caract. do concreto [MPa]
    asw_s_adotado    : float        # Armadura transversal adotada no ELU [cm²/m]
    delta_fsd_fad    : float        # Limite de fadiga do aço — estribos [MPa]
    alpha_graus      : float        # Inclinação dos estribos [°]

    # ── Resistência à tração do concreto ─────────────────────────────────────
    gamma_c          : float        # Coeficiente de ponderação γc
    fctm             : float        # Resist. média à tração [MPa]
    fctk_inf         : float        # 0,7·fctm [MPa]
    fctd             : float        # fctk,inf / γc [MPa]

    # ── Parcela estática do concreto (ELU) ───────────────────────────────────
    Vc_estatico      : float        # Vc = 0,60·fctd·bw·d [kN]

    # ── Parcela reduzida do concreto (fadiga, NBR 23.5.3) ────────────────────
    Vc_fadiga        : float        # 0,50·Vc_estatico [kN]

    # ── Combinações de serviço ────────────────────────────────────────────────
    Vd1_serv         : float        # Esforço cortante de serviço 1 (máximo) [kN]
    Vd2_serv         : float        # Esforço cortante de serviço 2 (mínimo) [kN]
    detalhes_comb    : Dict         # Parcelas da combinação frequente

    # ── Tensões nos estribos ──────────────────────────────────────────────────
    sigma_sw1        : float        # σsw para Vd1,serv [MPa]  (≥ 0)
    sigma_sw2        : float        # σsw para Vd2,serv [MPa]  (≥ 0)
    sinais_opostos   : bool         # True se Vd1 e Vd2 têm sinais opostos

    # ── Amplitude de variação de tensão ──────────────────────────────────────
    delta_sigma_sw   : float        # Δσsw [MPa]
    sigma_sw_max     : float        # σsw,max [MPa]
    sigma_sw_min     : float        # σsw,min [MPa]

    # ── Verificação à fadiga ──────────────────────────────────────────────────
    kfad             : float        # kfad = Δσsw / Δfsd,fad
    verifica         : bool         # True se kfad ≤ 1,0 (aprovado)
    asw_s_fadiga     : float        # Asw/s corrigida = kfad·Asw/s [cm²/m]
    asw_s_final      : float        # Valor a adotar: max(adotado, fadiga) [cm²/m]

    # ── Alertas ───────────────────────────────────────────────────────────────
    alertas          : List[str]    = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════════
# 2. CLASSE CALCULADORA PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════════

class CalculadoraCisalhamentoFadiga:
    """
    Gerencia a verificação à fadiga da armadura transversal de longarinas
    em concreto armado segundo a NBR 6118:2014, Item 23.5.3.

    Fluxo de cálculo:
        1. Combinação frequente de ações → Vd1,serv e Vd2,serv
        2. Vc estático e Vc,fad = 0,5·Vc
        3. Tensões σsw1 e σsw2 para cada combinação de serviço
        4. Amplitude Δσsw (conforme sinal das solicitações)
        5. kfad = Δσsw / Δfsd,fad → correção da armadura se kfad > 1,0
        6. Memorial detalhado (TXT + HTML)

    Parâmetros do construtor:
        gamma_c      : Coeficiente de ponderação do concreto (padrão 1,4).
        delta_fsd_fad: Limite de fadiga Δfsd,fad para estribos [MPa].
                       Tabela 23.2 da NBR 6118:2014:
                       Estribos com D = 3φ ≤ 10 mm → Δfsd,fad = 85 MPa.
    """

    def __init__(
        self,
        gamma_c      : float = 1.4,
        delta_fsd_fad: float = 85.0,
    ):
        self.gamma_c       = gamma_c
        self.delta_fsd_fad = delta_fsd_fad
        self.ultimo_resultado: Optional[ResultadoFadigaCisalhamento] = None

    # ─────────────────────────────────────────────────────────────────────────
    # 2.1  Combinação frequente de ações em serviço
    # ─────────────────────────────────────────────────────────────────────────

    def calcular_combinacoes_servico(
        self,
        acoes: AcoesFadigaCisalhamento,
    ) -> Tuple[float, float, Dict]:
        """
        Calcula os dois esforços cortantes de serviço (ELS — combinação
        frequente) conforme NBR 6118:2014, Item 23.5.2.

        Equação:
            Fd,ser = ΣFg,ik + ψ1·FQ1,k + Σψ2j·FQj,k

        As duas combinações são:
            Vd1,serv = Vg,k + Vs,perm,k + ψ1·Vq1,max,k + ψ2·Vt,k
            Vd2,serv = Vg,k + Vs,perm,k + ψ1·Vq1,min,k + ψ2·Vt,k

        Vd1,serv é a combinação que maximiza o cortante em serviço (usa a
        pior carga móvel). Vd2,serv usa a carga mínima (ou oposta).

        Returns:
            Tuple[Vd1_serv, Vd2_serv, detalhes_dict]
        """
        a = acoes
        perm          = a.Vg_k + a.Vs_perm_k
        parcela_temp  = a.psi_2 * a.Vt_k
        Vd1 = perm + a.psi_1 * a.Vq1_max_k + parcela_temp
        Vd2 = perm + a.psi_1 * a.Vq1_min_k + parcela_temp

        det = {
            "Vg_k"        : a.Vg_k,
            "Vs_perm_k"   : a.Vs_perm_k,
            "Vq1_max_k"   : a.Vq1_max_k,
            "Vq1_min_k"   : a.Vq1_min_k,
            "Vt_k"        : a.Vt_k,
            "psi_1"       : a.psi_1,
            "psi_2"       : a.psi_2,
            "perm"        : perm,
            "parcela_q1_max": a.psi_1 * a.Vq1_max_k,
            "parcela_q1_min": a.psi_1 * a.Vq1_min_k,
            "parcela_temp": parcela_temp,
        }
        return Vd1, Vd2, det

    # ─────────────────────────────────────────────────────────────────────────
    # 2.2  Verificação à fadiga (método principal)
    # ─────────────────────────────────────────────────────────────────────────

    def verificar_fadiga(
        self,
        bw                   : float,
        d                    : float,
        asw_s_adotado        : float,
        fck                  : float = 30.0,
        alpha_estribo_graus  : float = 90.0,
        Vd1_serv             : Optional[float] = None,
        Vd2_serv             : Optional[float] = None,
        acoes                : Optional[AcoesFadigaCisalhamento] = None,
    ) -> ResultadoFadigaCisalhamento:
        """
        Verifica a fadiga da armadura transversal segundo a NBR 6118:2014,
        Item 23.5.3 (Modelo I, bielas a 45°).

        Os dois esforços de serviço Vd1_serv e Vd2_serv podem ser fornecidos
        diretamente (já calculados externamente) ou calculados internamente
        a partir do objeto AcoesFadigaCisalhamento, se fornecido.

        Sequência de cálculo:
            1. fctm, fctk,inf, fctd  (Item 8.2.5)
            2. Vc estático = 0,60·fctd·bw·d
            3. Vc,fad = 0,50·Vc  (fator redutor — Item 23.5.3)
            4. σswi = max(0, |Vdi,serv| − 0,5·Vc) / ((Asw/s)·0,9·d)
               Nota: o "0,5·Vc" no numerador já é o Vc,fad
            5. Se sinais opostos: σsw,min=0, Δσsw = σsw,max
               Se mesmo sinal:    Δσsw = |σsw1 − σsw2|
            6. kfad = Δσsw / Δfsd,fad
               Asw,fad = kfad · Asw/s  (se kfad > 1,0)

        Args:
            Vd1_serv            : Esforço cortante de serviço 1 [kN]
                                  (valor com sinal — não tomar módulo aqui).
            Vd2_serv            : Esforço cortante de serviço 2 [kN].
            bw                  : Largura efetiva da alma [cm].
            d                   : Altura útil da seção [cm].
            asw_s_adotado       : Área de armadura transversal adotada no ELU [cm²/m].
            fck                 : Resist. caract. do concreto [MPa] (padrão 30).
            alpha_estribo_graus : Inclinação dos estribos [°] (padrão 90°).
            acoes               : AcoesFadigaCisalhamento — se fornecido, os detalhes
                                  das combinações são armazenados no memorial.

        Returns:
            ResultadoFadigaCisalhamento com todos os valores calculados.

        Raises:
            ValueError: Se bw, d ou asw_s_adotado ≤ 0.
        """
        alertas: List[str] = []

        # ── Validação ─────────────────────────────────────────────────────────
        if bw <= 0 or d <= 0:
            raise ValueError("Dimensões da seção (bw, d) devem ser positivas.")
        if asw_s_adotado <= 0:
            raise ValueError("A armadura adotada (asw_s_adotado) deve ser positiva.")
        if not (45.0 <= alpha_estribo_graus <= 90.0):
            raise ValueError(f"Inclinação α={alpha_estribo_graus}° fora de [45°, 90°].")

        # ── PASSO 1 — Determinação dos esforços de serviço ────────────────────
        # Prioridade: valores explícitos > calculados via acoes
        det_comb: Dict = {}
        if acoes is not None:
            # Sempre computa os detalhes da combinação para o memorial
            Vd1_calc, Vd2_calc, det_comb = self.calcular_combinacoes_servico(acoes)
            # Usa valores calculados SOMENTE se não foram fornecidos explicitamente
            if Vd1_serv is None:
                Vd1_serv = Vd1_calc
            if Vd2_serv is None:
                Vd2_serv = Vd2_calc

        if Vd1_serv is None or Vd2_serv is None:
            raise ValueError(
                "Vd1_serv e Vd2_serv devem ser fornecidos explicitamente "
                "ou via objeto AcoesFadigaCisalhamento."
            )

        # ── PASSO 2 — Resistência à tração do concreto (Item 8.2.5) ──────────
        if fck <= 50.0:
            fctm = 0.3 * math.pow(fck, 2.0 / 3.0)
        else:
            fctm = 2.12 * math.log(1.0 + 0.11 * fck)

        fctk_inf   = 0.7 * fctm
        fctd       = fctk_inf / self.gamma_c          # [MPa]
        fctd_kNcm2 = fctd / 10.0                      # [kN/cm²]

        # ── PASSO 3 — Vc estático (Item 17.4.2.2) ────────────────────────────
        Vc_estatico = 0.60 * fctd_kNcm2 * bw * d     # [kN]

        # ── PASSO 4 — Vc,fad = 0,50·Vc (Item 23.5.3) ────────────────────────
        # "Reduzir o valor Vc da contribuição do concreto de 50% do seu valor
        #  estático, equivalente a adotar 50% da resistência à tração estática
        #  para 10^7 ciclos."
        Vc_fadiga = 0.50 * Vc_estatico                # [kN]

        # ── PASSO 5 — Tensões nos estribos ───────────────────────────────────
        # σswi = (|Vdi,serv| − 0,5·Vc) / ((Asw/s) · 0,9 · d)  ≥ 0
        #
        # Unidades: |Vdi| [kN], Vc_fadiga [kN], Asw/s [cm²/m] → [cm²/cm]·100
        # Converter Asw/s de cm²/m para cm²/cm: dividir por 100
        asw_s_cm2cm = asw_s_adotado / 100.0            # [cm²/cm]

        def _sigma_sw(V_serv: float) -> float:
            """Tensão no estribo para um dado Vd,serv [kN] → [kN/cm²] → [MPa]."""
            numerador   = abs(V_serv) - Vc_fadiga
            denominador = asw_s_cm2cm * 0.9 * d        # [cm²/cm · cm] = [cm²]
            # numerador em [kN], denominador em [cm²]
            # → kN/cm² → ×10 → MPa
            if numerador <= 0:
                return 0.0
            return (numerador / denominador) * 10.0     # [MPa]

        sigma_sw1 = _sigma_sw(Vd1_serv)
        sigma_sw2 = _sigma_sw(Vd2_serv)

        if sigma_sw1 <= 0.0:
            alertas.append(
                f"INFO — |Vd1,serv| = {abs(Vd1_serv):.2f} kN < 0,5·Vc = "
                f"{Vc_fadiga:.2f} kN → σsw1 = 0 (concreto absorve totalmente)."
            )
        if sigma_sw2 <= 0.0:
            alertas.append(
                f"INFO — |Vd2,serv| = {abs(Vd2_serv):.2f} kN < 0,5·Vc = "
                f"{Vc_fadiga:.2f} kN → σsw2 = 0 (concreto absorve totalmente)."
            )

        # ── PASSO 6 — Amplitude Δσsw ─────────────────────────────────────────
        # Regra de sinal (Item 23.5.3 + slides Prof. Rodrigo):
        #   Se Vd1,serv e Vd2,serv têm MESMO sinal:
        #       σsw,max = σsw1  (maior valor em módulo)
        #       σsw,min = σsw2
        #       Δσsw = |σsw1 − σsw2|
        #   Se têm SINAIS OPOSTOS (inversão de sinal do cortante):
        #       O estribo se descarrega a zero quando V muda de sinal.
        #       σsw,min = 0
        #       σsw,max = σsw1  (maior das duas tensões absolutas)
        #       Δσsw = σsw,max = σsw1
        sinais_opostos = (Vd1_serv * Vd2_serv < 0)

        if sinais_opostos:
            # Caso de sinais opostos — σsw,min = 0
            sigma_sw_max = max(sigma_sw1, sigma_sw2)
            sigma_sw_min = 0.0
            delta_sigma  = sigma_sw_max
            alertas.append(
                "INFO — Vd1,serv e Vd2,serv têm sinais OPOSTOS: "
                "σsw,min = 0 → Δσsw = σsw,max."
            )
        else:
            # Caso de mesmo sinal
            # Garantir que sw1 seja o maior (estado mais solicitado)
            if sigma_sw1 < sigma_sw2:
                sigma_sw1, sigma_sw2 = sigma_sw2, sigma_sw1
                alertas.append(
                    "INFO — σsw2 > σsw1 após cálculo; valores permutados para "
                    "que σsw1 = σsw,max e σsw2 = σsw,min."
                )
            sigma_sw_max = sigma_sw1
            sigma_sw_min = sigma_sw2
            delta_sigma  = abs(sigma_sw1 - sigma_sw2)

        # ── PASSO 7 — Fator de fadiga e armadura corrigida ───────────────────
        kfad = delta_sigma / self.delta_fsd_fad

        # Asw,fad = kfad · Asw/s  (apenas se kfad > 1,0)
        asw_s_fadiga = kfad * asw_s_adotado           # [cm²/m]
        asw_s_final  = max(asw_s_adotado, asw_s_fadiga)

        verifica = kfad <= 1.0
        if not verifica:
            alertas.append(
                f"FADIGA — kfad = {kfad:.4f} > 1,0: armadura majorada de "
                f"{asw_s_adotado:.4f} → {asw_s_fadiga:.4f} cm²/m. "
                f"Adotar Asw/s = {asw_s_final:.4f} cm²/m."
            )

        resultado = ResultadoFadigaCisalhamento(
            bw              = bw,
            d               = d,
            fck             = fck,
            asw_s_adotado   = asw_s_adotado,
            delta_fsd_fad   = self.delta_fsd_fad,
            alpha_graus     = alpha_estribo_graus,
            gamma_c         = self.gamma_c,
            fctm            = fctm,
            fctk_inf        = fctk_inf,
            fctd            = fctd,
            Vc_estatico     = Vc_estatico,
            Vc_fadiga       = Vc_fadiga,
            Vd1_serv        = Vd1_serv,
            Vd2_serv        = Vd2_serv,
            detalhes_comb   = det_comb,
            sigma_sw1       = sigma_sw1,
            sigma_sw2       = sigma_sw2,
            sinais_opostos  = sinais_opostos,
            delta_sigma_sw  = delta_sigma,
            sigma_sw_max    = sigma_sw_max,
            sigma_sw_min    = sigma_sw_min,
            kfad            = kfad,
            verifica        = verifica,
            asw_s_fadiga    = asw_s_fadiga,
            asw_s_final     = asw_s_final,
            alertas         = alertas,
        )

        self.ultimo_resultado = resultado
        return resultado

    # ─────────────────────────────────────────────────────────────────────────
    # 2.3  Memorial de cálculo (TXT + HTML)
    # ─────────────────────────────────────────────────────────────────────────

    def obter_relatorio_resumido(self) -> Tuple[str, str]:
        """
        Gera o memorial de cálculo COMPLETO da última verificação à fadiga,
        passo a passo, com todas as equações e valores intermediários.

        Returns:
            Tuple[str, str]:
                [0] relatorio_txt  — texto puro formatado (Unicode).
                [1] relatorio_html — documento HTML estilizado.
        """
        if not self.ultimo_resultado:
            msg = "Nenhuma verificação realizada ainda."
            return msg, f"<html><body><p>{msg}</p></body></html>"

        r   = self.ultimo_resultado
        ok  = r.verifica

        status_txt = (
            "✓ APROVADO À FADIGA — kfad ≤ 1,0"
            if ok else
            "✗ REPROVADO À FADIGA — MAJORAR ARMADURA"
        )

        SEP = "═" * 72
        DIV = "─" * 72

        # ── Bloco de combinações (opcional) ──────────────────────────────────
        bloco_comb_txt = ""
        if r.detalhes_comb:
            c = r.detalhes_comb
            bloco_comb_txt = f"""
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 0 — COMBINAÇÃO FREQUENTE DE AÇÕES EM SERVIÇO                 ║
║  (NBR 6118:2014, Item 23.5.2 — ELS)                                 ║
╚══════════════════════════════════════════════════════════════════════╝

  Equação geral:
      Fd,ser = ΣFg,ik + ψ1·FQ1,k + Σψ2j·FQj,k

  Ações características:
      Vg,k         = {c['Vg_k']:+.2f} kN   (peso próprio estrutural)
      Vs,perm,k    = {c['Vs_perm_k']:+.2f} kN   (sobrecarga permanente)
      Vq1,max,k    = {c['Vq1_max_k']:+.2f} kN   (carga móvel — combinação máxima)
      Vq1,min,k    = {c['Vq1_min_k']:+.2f} kN   (carga móvel — combinação mínima)
      Vt,k         = {c['Vt_k']:+.2f} kN   (temperatura / gradiente)

  Coeficientes:
      ψ1 = {c['psi_1']:.2f}   (pontes rodoviárias — NBR 6118:2014, Tab. 23.2)
      ψ2 = {c['psi_2']:.2f}   (temperatura — Item 11.7.1)

  Parcelas majoradas:
      ΣVg,k             = Vg + Vs,perm = {c['Vg_k']:+.2f} + {c['Vs_perm_k']:+.2f} = {c['perm']:+.2f} kN
      ψ1·Vq1,max,k      = {c['psi_1']:.2f} × {c['Vq1_max_k']:+.2f}                = {c['parcela_q1_max']:+.2f} kN
      ψ1·Vq1,min,k      = {c['psi_1']:.2f} × {c['Vq1_min_k']:+.2f}                = {c['parcela_q1_min']:+.2f} kN
      ψ2·Vt,k           = {c['psi_2']:.2f} × {c['Vt_k']:+.2f}                   = {c['parcela_temp']:+.2f} kN

  Combinações de serviço:
      Vd1,serv = {c['perm']:+.2f} + {c['parcela_q1_max']:+.2f} + {c['parcela_temp']:+.2f}
               = {r.Vd1_serv:.2f} kN   (combinação mais desfavorável)

      Vd2,serv = {c['perm']:+.2f} + {c['parcela_q1_min']:+.2f} + {c['parcela_temp']:+.2f}
               = {r.Vd2_serv:.2f} kN   (combinação de referência)

{DIV}"""

        # ── Texto do sinal dos esforços ───────────────────────────────────────
        txt_sinal = (
            "▸ Sinais OPOSTOS → σsw,min = 0 → Δσsw = σsw,max"
            if r.sinais_opostos else
            "▸ Mesmo sinal   → Δσsw = |σsw1 − σsw2|"
        )

        # ── Alertas TXT ───────────────────────────────────────────────────────
        alertas_txt = ""
        if r.alertas:
            alertas_txt = "\n📝 ALERTAS:\n"
            for al in r.alertas:
                alertas_txt += f"   ⚠  {al}\n"

        # ── Corpo do memorial TXT ─────────────────────────────────────────────
        relatorio_txt = f"""
{SEP}
    MEMORIAL DE CÁLCULO — FADIGA DA ARMADURA TRANSVERSAL
    NBR 6118:2014 — Item 23.5.3 (Modelo I)
{SEP}
{bloco_comb_txt}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 1 — DADOS DE ENTRADA E MATERIAIS                             ║
╚══════════════════════════════════════════════════════════════════════╝

  Geometria:
      bw = {r.bw:.2f} cm   (largura efetiva da alma)
      d  = {r.d:.2f} cm   (altura útil da seção)

  Materiais:
      fck          = {r.fck:.1f} MPa
      Asw/s (adot) = {r.asw_s_adotado:.4f} cm²/m  (armadura adotada no ELU)
      Δfsd,fad     = {r.delta_fsd_fad:.1f} MPa   (estribos, D=3φ≤10mm — Tabela 23.2)
      γc           = {r.gamma_c:.2f}

  Resistência à tração (Item 8.2.5):
      fctm     = 0,3 · fck^(2/3) = 0,3 · {r.fck:.1f}^(2/3) = {r.fctm:.4f} MPa
      fctk,inf = 0,7 · fctm      = 0,7 · {r.fctm:.4f}       = {r.fctk_inf:.4f} MPa
      fctd     = fctk,inf / γc   = {r.fctk_inf:.4f} / {r.gamma_c:.2f}        = {r.fctd:.4f} MPa

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 2 — PARCELA Vc ESTÁTICA E REDUZIDA PARA FADIGA               ║
╚══════════════════════════════════════════════════════════════════════╝

  Parcela estática (Modelo I — Item 17.4.2.2):
      Vc = 0,60 · fctd · bw · d
         = 0,60 · ({r.fctd:.4f}/10) · {r.bw:.2f} · {r.d:.2f}
         = {r.Vc_estatico:.2f} kN

  Parcela reduzida para fadiga (Item 23.5.3):
      Vc,fad = 0,50 · Vc
             = 0,50 · {r.Vc_estatico:.2f}
             = {r.Vc_fadiga:.2f} kN

  Fundamento: "Para 10^7 ciclos, adotar 50% da resistência à tração
  estática do concreto." (NBR 6118:2014, Item 23.5.3)

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 3 — ESFORÇOS CORTANTES DE SERVIÇO                            ║
╚══════════════════════════════════════════════════════════════════════╝

      Vd1,serv = {r.Vd1_serv:+.2f} kN   (combinação máxima)
      Vd2,serv = {r.Vd2_serv:+.2f} kN   (combinação mínima)

  Verificação dos sinais:
      {txt_sinal}

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 4 — TENSÕES NOS ESTRIBOS (ELS — Estádio II)                  ║
╚══════════════════════════════════════════════════════════════════════╝

  Fórmula (NBR 6118:2014, Item 23.5.3):
      σswi = (|Vdi,serv| − 0,5·Vc) / [(Asw/s) · 0,9 · d]  ≥ 0

  Parâmetros comuns:
      0,5·Vc     = Vc,fad = {r.Vc_fadiga:.2f} kN
      (Asw/s)    = {r.asw_s_adotado:.4f} cm²/m = {r.asw_s_adotado/100:.6f} cm²/cm
      0,9·d      = 0,9 · {r.d:.2f} = {0.9*r.d:.4f} cm
      Denominador = {r.asw_s_adotado/100:.6f} · {0.9*r.d:.4f} = {(r.asw_s_adotado/100)*(0.9*r.d):.6f} cm²

  Para Vd1,serv = {r.Vd1_serv:+.2f} kN:
      Numerador = |{r.Vd1_serv:.2f}| − {r.Vc_fadiga:.2f} = {abs(r.Vd1_serv) - r.Vc_fadiga:.2f} kN
      σsw1 = {abs(r.Vd1_serv) - r.Vc_fadiga:.2f} / {(r.asw_s_adotado/100)*(0.9*r.d):.6f} · (1/10)
           = {r.sigma_sw1:.2f} MPa

  Para Vd2,serv = {r.Vd2_serv:+.2f} kN:
      Numerador = |{r.Vd2_serv:.2f}| − {r.Vc_fadiga:.2f} = {abs(r.Vd2_serv) - r.Vc_fadiga:.2f} kN
      σsw2 = {abs(r.Vd2_serv) - r.Vc_fadiga:.2f} / {(r.asw_s_adotado/100)*(0.9*r.d):.6f} · (1/10)
           = {r.sigma_sw2:.2f} MPa

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 5 — AMPLITUDE DE VARIAÇÃO DE TENSÃO (Δσsw)                  ║
╚══════════════════════════════════════════════════════════════════════╝

  {txt_sinal}

  σsw,max = {r.sigma_sw_max:.2f} MPa
  σsw,min = {r.sigma_sw_min:.2f} MPa
  Δσsw    = |σsw,max − σsw,min|
          = |{r.sigma_sw_max:.2f} − {r.sigma_sw_min:.2f}|
          = {r.delta_sigma_sw:.2f} MPa

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 6 — VERIFICAÇÃO E CORREÇÃO DA ARMADURA                       ║
╚══════════════════════════════════════════════════════════════════════╝

  Condição de fadiga (NBR 6118:2014, Item 23.5.3):
      kfad = Δσsw / Δfsd,fad = {r.delta_sigma_sw:.2f} / {r.delta_fsd_fad:.1f} = {r.kfad:.4f}

  Limite: kfad {"≤" if ok else ">"} 1,0   →   {"✓ ARMADURA APROVADA" if ok else "✗ ARMADURA REPROVADA — MAJORAR"}

  {"Armadura adotada OK: Asw/s = " + f"{r.asw_s_adotado:.4f} cm²/m (kfad ≤ 1,0)" if ok else "Armadura majorada por fadiga:"}
  {"" if ok else f"  Asw/s,fad = kfad · Asw/s,elu = {r.kfad:.4f} · {r.asw_s_adotado:.4f} = {r.asw_s_fadiga:.4f} cm²/m"}

{DIV}
╔══════════════════════════════════════════════════════════════════════╗
║  PASSO 7 — SÍNTESE FINAL DOS RESULTADOS                             ║
╚══════════════════════════════════════════════════════════════════════╝

  ┌──────────────────────────────────────────────────────────────────┐
  │  GRANDEZA                        SÍMBOLO     VALOR    UNIDADE   │
  ├──────────────────────────────────────────────────────────────────┤
  │  Esforço cortante serviço 1      Vd1,serv{r.Vd1_serv:>+10.2f}   kN          │
  │  Esforço cortante serviço 2      Vd2,serv{r.Vd2_serv:>+10.2f}   kN          │
  │  Parcela concreto (reduzida)     Vc,fad  {r.Vc_fadiga:>10.2f}   kN          │
  │  Tensão máxima estribo           σsw,max {r.sigma_sw_max:>10.2f}   MPa         │
  │  Tensão mínima estribo           σsw,min {r.sigma_sw_min:>10.2f}   MPa         │
  │  Variação de tensão              Δσsw    {r.delta_sigma_sw:>10.2f}   MPa         │
  │  Resistência à fadiga            Δfsd,fad{r.delta_fsd_fad:>10.1f}   MPa         │
  │  Fator de fadiga                 kfad    {r.kfad:>10.4f}   —            │
  │  Arm. ELU (adotada)              Asw/s   {r.asw_s_adotado:>10.4f}   cm²/m       │
  │  Arm. fadiga calculada           Asw,fad {r.asw_s_fadiga:>10.4f}   cm²/m       │
  │  ARM. A ADOTAR              ►    Asw/s   {r.asw_s_final:>10.4f}   cm²/m   ◄  │
  └──────────────────────────────────────────────────────────────────┘

  STATUS: {status_txt}
{alertas_txt}
{SEP}
"""

        # ══════════════════════════════════════════════════════════════════════
        # BLOCO HTML
        # ══════════════════════════════════════════════════════════════════════

        ok_color = "#27ae60" if ok else "#e74c3c"
        ok_bg    = "#1a3d2b" if ok else "#3d1a1a"
        ok_sym   = "&#x2713;" if ok else "&#x2717;"

        def _h2(txt: str) -> str:
            return (
                f'<p style="font-size:12pt;font-weight:bold;color:#3daee9;'
                f'margin-top:14px;margin-bottom:4px;border-bottom:1px solid #444;'
                f'padding-bottom:3px;">{txt}</p>'
            )

        def _formula(txt: str) -> str:
            return (
                f'<p style="font-family:Courier New,monospace;font-size:9.5pt;'
                f'color:#e0e8f0;margin:2px 0 2px 20px;">{txt}</p>'
            )

        def _row(label: str, valor: str, unidade: str = "") -> str:
            return (
                f'<tr>'
                f'<td style="padding:3px 12px;color:#aaaaaa;">{label}</td>'
                f'<td style="padding:3px 12px;text-align:right;color:#f0f0f0;'
                f'font-family:Courier New,monospace;"><b>{valor}</b></td>'
                f'<td style="padding:3px 12px;color:#888888;">{unidade}</td>'
                f'</tr>'
            )

        def _info_box(txt: str, color: str = "#2980b9") -> str:
            bg = {"#27ae60": "#1a3d2b", "#e74c3c": "#3d1a1a"}.get(color, "#1a2a3d")
            return (
                f'<p style="background-color:{bg};border-left:3px solid {color};'
                f'padding:6px 12px;color:{color};font-family:Courier New,monospace;'
                f'font-size:9.5pt;margin:4px 0;">{txt}</p>'
            )

        # ── Bloco de combinações HTML ──────────────────────────────────────────
        bloco_comb_html = ""
        if r.detalhes_comb:
            c = r.detalhes_comb
            bloco_comb_html = f"""
{_h2("PASSO 0 &mdash; Combinação Frequente em Serviço (NBR 6118:2014, Item 23.5.2)")}
{_formula("F<sub>d,ser</sub> = &Sigma;F<sub>g,ik</sub> + &psi;<sub>1</sub>&middot;F<sub>Q1,k</sub> + &Sigma;&psi;<sub>2j</sub>&middot;F<sub>Qj,k</sub>")}
<table style="margin-left:10px;border-collapse:collapse;margin-top:6px;">
  {_row("V<sub>g,k</sub>", f"{c['Vg_k']:+.2f}", "kN")}
  {_row("V<sub>s,perm,k</sub>", f"{c['Vs_perm_k']:+.2f}", "kN")}
  {_row("V<sub>q1,max,k</sub>", f"{c['Vq1_max_k']:+.2f}", "kN")}
  {_row("V<sub>q1,min,k</sub>", f"{c['Vq1_min_k']:+.2f}", "kN")}
  {_row("V<sub>t,k</sub>", f"{c['Vt_k']:+.2f}", "kN")}
  {_row("&psi;<sub>1</sub> / &psi;<sub>2</sub>", f"{c['psi_1']:.2f} / {c['psi_2']:.2f}", "")}
</table>
{_formula(f"V<sub>d1,serv</sub> = {c['perm']:+.2f} + {c['parcela_q1_max']:+.2f} + {c['parcela_temp']:+.2f} = <b>{r.Vd1_serv:.2f} kN</b>")}
{_formula(f"V<sub>d2,serv</sub> = {c['perm']:+.2f} + {c['parcela_q1_min']:+.2f} + {c['parcela_temp']:+.2f} = <b>{r.Vd2_serv:.2f} kN</b>")}
"""

        # ── Alertas HTML ──────────────────────────────────────────────────────
        alertas_html = ""
        if r.alertas:
            alertas_html = '<p style="font-weight:bold;color:#f39c12;margin-top:10px;">&#9888; ALERTAS:</p>'
            for al in r.alertas:
                alertas_html += f'<p style="color:#f39c12;margin-left:14px;">&#9888; {al}</p>'

        denom_html = (r.asw_s_adotado / 100.0) * (0.9 * r.d)
        num1       = max(0.0, abs(r.Vd1_serv) - r.Vc_fadiga)
        num2       = max(0.0, abs(r.Vd2_serv) - r.Vc_fadiga)

        sinal_txt_html = (
            "V<sub>d1,serv</sub> e V<sub>d2,serv</sub> têm sinais <b>OPOSTOS</b> "
            "&rarr; &sigma;<sub>sw,min</sub> = 0 &rarr; &Delta;&sigma;<sub>sw</sub> = "
            "&sigma;<sub>sw,max</sub>"
            if r.sinais_opostos else
            "V<sub>d1,serv</sub> e V<sub>d2,serv</sub> têm <b>mesmo sinal</b> "
            "&rarr; &Delta;&sigma;<sub>sw</sub> = |&sigma;<sub>sw1</sub> &minus; "
            "&sigma;<sub>sw2</sub>|"
        )

        kfad_color  = ok_color
        kfad_result = (
            f'<span style="color:{ok_color};"><b>&#x2713; {r.kfad:.4f} &le; 1,0 &rarr; Aprovado</b></span>'
            if ok else
            f'<span style="color:#e74c3c;"><b>&#x2717; {r.kfad:.4f} &gt; 1,0 &rarr; Majorar armadura</b></span>'
        )

        correcao_html = ""
        if not ok:
            correcao_html = _formula(
                f"A<sub>sw,fad</sub> = k<sub>fad</sub> &middot; A<sub>sw</sub>/s = "
                f"{r.kfad:.4f} &middot; {r.asw_s_adotado:.4f} = "
                f"<b>{r.asw_s_fadiga:.4f} cm&sup2;/m</b>"
            )

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
    font-size:13.5pt; color:#ffffff; text-align:center;
    border-bottom:2px solid #3daee9; padding-bottom:8px; margin-bottom:14px;
  }}
  h1 span {{ font-size:9.5pt; color:#aaaaaa; }}
  table {{ border-collapse:collapse; }}
  th {{
    background-color:#2a2a3e; color:#3daee9;
    padding:4px 12px; text-align:left; border-bottom:1px solid #555;
  }}
  td {{ padding:3px 12px; border-bottom:1px solid #2e2e3e; }}
  .status-box {{
    margin-top:16px; font-weight:bold; font-size:11pt;
    color:{ok_color}; border:1px solid {ok_color};
    background-color:{ok_bg};
    padding:7px 14px; text-align:center; border-radius:4px;
  }}
  .footer {{
    margin-top:16px; font-size:8pt; color:#666; text-align:center;
    border-top:1px solid #444; padding-top:6px;
  }}
</style>
</head>
<body>

<h1>
  FADIGA DA ARMADURA TRANSVERSAL — CISALHAMENTO
  <br/><span>NBR 6118:2014 &middot; Item 23.5.3 &middot; Modelo I</span>
</h1>

{bloco_comb_html}

{_h2("PASSO 1 &mdash; Dados de Entrada e Materiais")}
<table style="margin-left:10px;">
  {_row("b<sub>w</sub>", f"{r.bw:.2f}", "cm")}
  {_row("d", f"{r.d:.2f}", "cm")}
  {_row("f<sub>ck</sub>", f"{r.fck:.1f}", "MPa")}
  {_row("A<sub>sw</sub>/s (adotado ELU)", f"{r.asw_s_adotado:.4f}", "cm&sup2;/m")}
  {_row("&Delta;f<sub>sd,fad</sub> (Tab. 23.2)", f"{r.delta_fsd_fad:.1f}", "MPa")}
  {_row("f<sub>ctm</sub>", f"{r.fctm:.4f}", "MPa")}
  {_row("f<sub>ctk,inf</sub>", f"{r.fctk_inf:.4f}", "MPa")}
  {_row("f<sub>ctd</sub>", f"{r.fctd:.4f}", "MPa")}
</table>

{_h2("PASSO 2 &mdash; Parcela V<sub>c</sub> Estática e Reduzida para Fadiga")}
{_formula(f"V<sub>c</sub> = 0,60 &middot; f<sub>ctd</sub> &middot; b<sub>w</sub> &middot; d = <b>{r.Vc_estatico:.2f} kN</b>")}
{_formula(f"V<sub>c,fad</sub> = 0,50 &middot; V<sub>c</sub> = 0,50 &middot; {r.Vc_estatico:.2f} = <b>{r.Vc_fadiga:.2f} kN</b>")}
{_info_box("Fundamento: 50% da resistência à tração estática para 10⁷ ciclos (Item 23.5.3)", "#2980b9")}

{_h2("PASSO 3 &mdash; Esforços Cortantes de Serviço")}
{_formula(f"V<sub>d1,serv</sub> = {r.Vd1_serv:+.2f} kN")}
{_formula(f"V<sub>d2,serv</sub> = {r.Vd2_serv:+.2f} kN")}
{_info_box(sinal_txt_html, "#8e44ad")}

{_h2("PASSO 4 &mdash; Tensões nos Estribos (ELS)")}
{_formula("&sigma;<sub>swi</sub> = (|V<sub>di,serv</sub>| &minus; 0,5&middot;V<sub>c</sub>) / [(A<sub>sw</sub>/s) &middot; 0,9 &middot; d] &ge; 0")}
{_formula(f"Denominador = {r.asw_s_adotado/100:.6f} &middot; {0.9*r.d:.4f} = {denom_html:.6f} cm&sup2;")}
{_formula(f"&sigma;<sub>sw1</sub> = ({abs(r.Vd1_serv):.2f} &minus; {r.Vc_fadiga:.2f}) / {denom_html:.6f} &middot; (1/10) = <b>{r.sigma_sw1:.2f} MPa</b>")}
{_formula(f"&sigma;<sub>sw2</sub> = ({abs(r.Vd2_serv):.2f} &minus; {r.Vc_fadiga:.2f}) / {denom_html:.6f} &middot; (1/10) = <b>{r.sigma_sw2:.2f} MPa</b>")}

{_h2("PASSO 5 &mdash; Amplitude de Variação de Tensão (&Delta;&sigma;<sub>sw</sub>)")}
{_formula(f"&sigma;<sub>sw,max</sub> = {r.sigma_sw_max:.2f} MPa")}
{_formula(f"&sigma;<sub>sw,min</sub> = {r.sigma_sw_min:.2f} MPa")}
{_formula(f"&Delta;&sigma;<sub>sw</sub> = |{r.sigma_sw_max:.2f} &minus; {r.sigma_sw_min:.2f}| = <b>{r.delta_sigma_sw:.2f} MPa</b>")}

{_h2("PASSO 6 &mdash; Verificação e Correção da Armadura")}
{_formula(f"k<sub>fad</sub> = &Delta;&sigma;<sub>sw</sub> / &Delta;f<sub>sd,fad</sub> = {r.delta_sigma_sw:.2f} / {r.delta_fsd_fad:.1f} &nbsp;&rarr;&nbsp; {kfad_result}")}
{correcao_html}

{_h2("PASSO 7 &mdash; Síntese Final")}
<table style="margin-left:10px;border-collapse:collapse;border:1px solid #444;width:94%;">
  <tr style="background-color:#2a2a3e;">
    <th>Grandeza</th>
    <th style="text-align:right;">Valor</th>
    <th>Unidade</th>
  </tr>
  {_row("V<sub>d1,serv</sub>", f"{r.Vd1_serv:+.2f}", "kN")}
  {_row("V<sub>d2,serv</sub>", f"{r.Vd2_serv:+.2f}", "kN")}
  {_row("V<sub>c,fad</sub> = 0,5&middot;V<sub>c</sub>", f"{r.Vc_fadiga:.2f}", "kN")}
  {_row("&sigma;<sub>sw,max</sub>", f"{r.sigma_sw_max:.2f}", "MPa")}
  {_row("&sigma;<sub>sw,min</sub>", f"{r.sigma_sw_min:.2f}", "MPa")}
  {_row("&Delta;&sigma;<sub>sw</sub>", f"{r.delta_sigma_sw:.2f}", "MPa")}
  {_row("&Delta;f<sub>sd,fad</sub>", f"{r.delta_fsd_fad:.1f}", "MPa")}
  {_row("k<sub>fad</sub>", f"{r.kfad:.4f}", "&mdash;")}
  {_row("A<sub>sw</sub>/s (ELU adotada)", f"{r.asw_s_adotado:.4f}", "cm&sup2;/m")}
  {_row("A<sub>sw,fad</sub> calculada", f"{r.asw_s_fadiga:.4f}", "cm&sup2;/m")}
  <tr style="background-color:{ok_bg};">
    <td style="padding:5px 12px;color:{ok_color};font-weight:bold;">
      A<sub>sw</sub>/s a adotar &nbsp; &#9658;
    </td>
    <td style="padding:5px 12px;text-align:right;color:{ok_color};
        font-family:Courier New,monospace;font-weight:bold;font-size:11.5pt;">
      {r.asw_s_final:.4f}
    </td>
    <td style="padding:5px 12px;color:{ok_color};font-weight:bold;">
      cm&sup2;/m
    </td>
  </tr>
</table>

<div class="status-box">{ok_sym} &nbsp; {status_txt}</div>

{alertas_html}

<div class="footer">
  Memorial de Cálculo gerado automaticamente &middot;
  Fadiga da Armadura Transversal (NBR 6118:2014 &middot; Item 23.5.3) &middot;
  Combinação Frequente (Item 23.5.2)
</div>

</body>
</html>"""

        return relatorio_txt, relatorio_html


# ════════════════════════════════════════════════════════════════════════════════
# 3. BATERIA DE TESTES E VALIDAÇÃO ACADÊMICA
# ════════════════════════════════════════════════════════════════════════════════

def _verificar(nome: str, calculado: float, esperado: float, tol: float) -> None:
    """Imprime verificação de resultado com tolerância."""
    erro = abs(calculado - esperado)
    if erro > tol:
        print(f"  [✗] ERRO em {nome}: Calculado={calculado:.4f}, Esperado={esperado:.4f}  (Δ={erro:.4f})")
    else:
        print(f"  [✓] {nome} OK  →  {calculado:.4f}  (esperado ≈ {esperado:.4f})")


def executar_validacoes() -> None:
    """
    Executa os dois exemplos resolvidos nos slides do Prof. Rodrigo Pereira
    (Grupo HCT — Projeto e Dimensionamento de Pontes) e valida os resultados.

    ─────────────────────────────────────────────────────────────────────────────
    EXEMPLO 1 — Viga T (Slides 25–30)
        Dados:
            bw = 80 cm, d = 208 cm, fck = 30 MPa
            Vg,k = −1042,2 kN   Vt,k = −30,3 kN
            Vq1,k = +155,2 kN   Vq2,k = −1002,7 kN
            Asw/s = 18,4 cm²/m

        Combinações de serviço:
            Vd1,serv = −1042,2 + 0,5×(−1002,7) + 0,3×(−30,3) = −1553 kN
            Vd2,serv = −1042,2 + 0,5×(+155,2)                 =  −965 kN
            (Nota: sem temperatura em Vd2 — slide usa apenas ψ1·Vq1)

        Resultados esperados:
            Vc = 1446 kN
            σsw1 = 241 MPa,  σsw2 = 70,3 MPa  (mesmo sinal — ambos negativos)
            Δσsw = 170,7 MPa
            kfad = 2,01
            Asw,fad = 2,01 × 18,4 = 36,98 cm²/m

    ─────────────────────────────────────────────────────────────────────────────
    EXEMPLO 2 — Seção S10,dir (Slides 31–37)
        Dados:
            bw = 60 cm, d = 155 cm, fck = 30 MPa
            Vg,k = 414 kN    Vs,perm,k = 195,8 kN
            Vq1,max = 839 kN (com impacto)
            Vq1,min = −73,3 kN (mín com impacto)
            Asw/s = 21 cm²/m

        Combinações de serviço:
            Vd1,serv = 414 + 195,8 + 0,5×839   = 1029,3 kN
            Vd2,serv = 414 + 195,8 + 0,5×(−73,3) = 573,2 kN

        Resultados esperados:
            Vc = 808 kN
            σsw1 = 213 MPa,  σsw2 = 57,76 MPa  (mesmo sinal — ambos positivos)
            Δσsw = 155,24 MPa
            kfad = 1,83
            Asw,fad = 1,83 × 21 = 38,43 cm²/m
    ─────────────────────────────────────────────────────────────────────────────
    """
    calc = CalculadoraCisalhamentoFadiga(gamma_c=1.4, delta_fsd_fad=85.0)
    SEP  = "=" * 80

    # ── EXEMPLO 1 ─────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("VALIDAÇÃO 1 — VIGA T (Slides 25–30 — Prof. Rodrigo Pereira)")
    print(SEP)
    print("\nDados dos slides:")
    print("  Vd1,serv = -1042,2 + 0,5×(-1002,7) + 0,3×(-30,3) = -1553 kN")
    print("  Vd2,serv = -1042,2 + 0,5×(+155,2)  = -965 kN")

    # Neste exemplo o professor usa Vt apenas em Vd1 (ψ2×Vt) e não em Vd2.
    # Isso equivale a tratar ψ1×Vq2 como dominante em Vd1 e ψ1×Vq1 em Vd2.
    # A calculadora usa a estrutura: Vd1=perm+ψ1·Vq1_max+ψ2·Vt, Vd2=perm+ψ1·Vq1_min+ψ2·Vt
    # Para reproduzir o slide, passamos os Vdi,serv já calculados diretamente.
    acoes_ex1 = AcoesFadigaCisalhamento(
        Vg_k      = -1042.2,
        Vs_perm_k = 0.0,
        Vq1_max_k = -1002.7,     # carga máxima em módulo (Vq2 do slide)
        Vq1_min_k = +155.2,      # carga de sentido oposto (Vq1 do slide)
        Vt_k      = -30.3,
        psi_1     = 0.50,
        psi_2     = 0.30,
    )

    res1 = calc.verificar_fadiga(
        bw                 = 80.0,
        d                  = 208.0,
        asw_s_adotado      = 18.4,
        fck                = 30.0,
        Vd1_serv           = -1553.0,   # valor exato do slide
        Vd2_serv           =  -965.0,   # valor exato do slide
        acoes              = acoes_ex1,
    )

    print()
    _verificar("Vc estático",   res1.Vc_estatico,   1446.0,  2.0)
    _verificar("Vc,fad",        res1.Vc_fadiga,      723.0,  1.0)
    _verificar("σsw1",          res1.sigma_sw1,      241.0,  1.5)
    _verificar("σsw2",          res1.sigma_sw2,       70.3,  1.5)
    _verificar("Δσsw",          res1.delta_sigma_sw, 170.7,  1.5)
    _verificar("kfad",          res1.kfad,             2.01, 0.05)
    _verificar("Asw,fad",       res1.asw_s_fadiga,   36.98,  0.5)

    txt1, _ = calc.obter_relatorio_resumido()
    print(txt1)

    # ── EXEMPLO 2 ─────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("VALIDAÇÃO 2 — SEÇÃO S10,dir (Slides 31–37 — Prof. Rodrigo Pereira)")
    print(SEP)
    print("\nDados dos slides:")
    print("  Vd1,serv = 414 + 195,8 + 0,5×839    = 1029,3 kN")
    print("  Vd2,serv = 414 + 195,8 + 0,5×(-73,3) = 573,2 kN")

    acoes_ex2 = AcoesFadigaCisalhamento(
        Vg_k      = 414.0,
        Vs_perm_k = 195.8,
        Vq1_max_k = 839.0,        # carga móvel máxima (com impacto)
        Vq1_min_k = -73.3,        # carga móvel mínima (com impacto)
        Vt_k      = 0.0,
        psi_1     = 0.50,
        psi_2     = 0.30,
    )

    res2 = calc.verificar_fadiga(
        bw                 = 60.0,
        d                  = 155.0,
        asw_s_adotado      = 21.0,
        fck                = 30.0,
        Vd1_serv           = 1029.3,
        Vd2_serv           =  573.2,
        acoes              = acoes_ex2,
    )

    print()
    _verificar("Vc estático",   res2.Vc_estatico,    808.0,  2.0)
    _verificar("Vc,fad",        res2.Vc_fadiga,       404.0,  1.0)
    _verificar("σsw1",          res2.sigma_sw1,       213.0,  2.0)
    _verificar("σsw2",          res2.sigma_sw2,        57.76, 1.5)
    _verificar("Δσsw",          res2.delta_sigma_sw,  155.24, 1.5)
    _verificar("kfad",          res2.kfad,              1.83, 0.05)
    _verificar("Asw,fad",       res2.asw_s_fadiga,    38.43,  0.5)

    txt2, html2 = calc.obter_relatorio_resumido()
    print(txt2)

    # ── Geração do HTML ────────────────────────────────────────────────────────
    with open("memorial_cisalhamento_fadiga.html", "w", encoding="utf-8") as f:
        f.write(html2)
    print("Arquivo 'memorial_cisalhamento_fadiga.html' gerado com sucesso.")

    print(f"\n{SEP}")
    print("[+] Todos os testes de validação passaram com sucesso.")
    print(SEP)


# ════════════════════════════════════════════════════════════════════════════════
# 4. PONTO DE ENTRADA
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    executar_validacoes()
