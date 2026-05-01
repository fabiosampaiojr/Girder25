"""
Calculadora_Flexao_Fadiga.py
================================================================================
Módulo avançado para Verificação à Fadiga das armaduras de flexão (Estádio II).
Baseado nas diretrizes da NBR 6118:2014 e exemplos acadêmicos rigorosos.
O cálculo de Estádio II (seção fissurada) utiliza um motor numérico universal 
de integração por fatias e bissecção. Isso permite calcular a linha neutra (x) 
e a inércia fissurada (J_fiss) para QUALQUER formato de seção (Retangular, T, I),
com ou sem laje colaborante, sem depender de longas formulações algébricas.
Funcionalidades:
    • Cálculo rigoroso do Estádio II (x, J_fiss, tensões).
    • Suporte automático a momentos positivos (compressão no topo) e 
      momentos negativos (compressão na base / seção invertida).
    • Armadura dupla (considerando homogenização com fator 'n').
    • Limites de fadiga independentes para armadura inferior e superior
      (delta_f_fad_sd_inf e delta_f_fad_sd_sup).
    • Fator de aproveitamento eta (η) para correção de armadura reprovada.
    • Cálculo automático da armadura corrigida (as_inf_corrigida / as_sup_corrigida)
      quando a verificação de fadiga não é satisfeita.
    • Geração de memoriais de cálculo extremamente detalhados em Texto e HTML,
      incluindo todas as etapas intermediárias (fatias, bissecção, inércias,
      tensões e verificações passo a passo).
Autor: Assistente AI de Engenharia
Data: 2026
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum

# ════════════════════════════════════════════════════════════════════════════════
# 1. ESTRUTURAS DE DADOS
# ════════════════════════════════════════════════════════════════════════════════

class TipoSecao(Enum):
    RETANGULAR = "Retangular"
    T = "T"
    I = "I"


@dataclass
class ResultadoEstadioII:
    """Resultados do cálculo do Estádio II para um dado momento fletor."""
    momento_sd     : float  # Momento solicitante [kN.m]
    is_negativo    : bool   # True se momento < 0 (compressão na base)
    x_cm           : float  # Posição da L.N. medida da borda MAIS COMPRIMIDA [cm]
    Jfiss_cm4      : float  # Inércia fissurada homogenizada [cm⁴]
    sigma_inf_MPa  : float  # Tensão na armadura INFERIOR [MPa] (+ Tração, - Comp)
    sigma_sup_MPa  : float  # Tensão na armadura SUPERIOR [MPa] (+ Tração, - Comp)


@dataclass
class ResultadoFadiga:
    """Resultado final da verificação à fadiga comparando dois momentos."""
    res_M1               : ResultadoEstadioII
    res_M2               : ResultadoEstadioII
    eta                  : float  # Fator de aproveitamento/eficiência para correção da armadura
    delta_f_fad_sd_inf   : float  # Resistência à fadiga do aço – armadura INFERIOR [MPa]
    delta_f_fad_sd_sup   : float  # Resistência à fadiga do aço – armadura SUPERIOR [MPa]

    delta_sigma_inf_MPa  : float          # Variação de tensão armadura inferior [MPa]
    k_fad_inf            : float          # Coeficiente de utilização inferior (Δσ / Δf_fad)
    verifica_inf         : bool           # True se k_fad_inf <= 1.0
    as_inf_corrigida     : Union[str, float]  # "Não houve necessidade de correção" ou valor [cm²]

    delta_sigma_sup_MPa  : float          # Variação de tensão armadura superior [MPa]
    k_fad_sup            : float          # Coeficiente de utilização superior
    verifica_sup         : bool           # True se k_fad_sup <= 1.0
    as_sup_corrigida     : Union[str, float]  # "Não houve necessidade de correção" ou valor [cm²]


# ════════════════════════════════════════════════════════════════════════════════
# 2. MOTOR DE CÁLCULO NUMÉRICO (ESTÁDIO II)
# ════════════════════════════════════════════════════════════════════════════════

class MotorEstadioII:
    """
    Motor universal de integração de seções de concreto para o Estádio II.
    A base do cálculo assume o eixo y=0 sempre na borda MAIS COMPRIMIDA.
    """

    def __init__(
        self,
        dados_secao : Dict,
        n_eq        : float,
        As_inf      : float,
        d_inf       : float,
        As_sup      : float = 0.0,
        d_sup       : float = 0.0,
        h_laje      : float = 0.0,
        b_laje      : float = 0.0
    ):
        self.dados  = dados_secao
        self.n      = float(n_eq)
        self.As_inf = float(As_inf)
        self.d_inf  = float(d_inf)
        self.As_sup = float(As_sup)
        self.d_sup  = float(d_sup)
        self.h_laje = float(h_laje)
        self.b_laje = float(b_laje)
        # Altura total (importante para inverter a seção nos momentos negativos)
        self.H_total = float(self.dados.get("h", 0)) + self.h_laje

    def _gerar_fatias(self, momento_negativo: bool) -> List[Tuple[float, float, float]]:
        """
        Retorna a seção como lista de retângulos (y_inicio, y_fim, largura).
        Se M < 0, a seção é rotacionada em 180° para manter y=0 comprimido.
        """
        fatias = []
        y = 0.0

        # 1. Laje colaborante (fica no topo estrutural)
        if self.h_laje > 0 and self.b_laje > 0:
            fatias.append((y, y + self.h_laje, self.b_laje))
            y += self.h_laje

        tipo = self.dados.get("Tipo", "Retangular")

        # 2. Geometria da Viga
        if tipo == TipoSecao.RETANGULAR.value:
            b = float(self.dados.get("bw", self.dados.get("b", 0)))
            fatias.append((y, y + float(self.dados["h"]), b))

        elif tipo == TipoSecao.T.value:
            bw, h  = float(self.dados["bw"]), float(self.dados["h"])
            bf, hf = float(self.dados["bf"]), float(self.dados["hf"])
            fatias.append((y, y + hf, bf))
            fatias.append((y + hf, y + h, bw))

        elif tipo == TipoSecao.I.value:
            bw, h         = float(self.dados["bw"]), float(self.dados["h"])
            btf, hft      = float(self.dados["btf"]), float(self.dados["hft"])
            bfb, hfb      = float(self.dados["bfb"]), float(self.dados["hfb"])
            fatias.append((y, y + hft, btf))
            fatias.append((y + hft, y + h - hfb, bw))
            fatias.append((y + h - hfb, y + h, bfb))

        # Se for Momento Positivo, o topo já está em y=0. Retorna as fatias.
        if not momento_negativo:
            return fatias

        # Se for Momento Negativo, inverte as coordenadas.
        H = self.H_total
        invertidas = [(H - y2, H - y1, b) for (y1, y2, b) in fatias]
        return sorted(invertidas, key=lambda f: f[0])

    def _mapear_armaduras(self, momento_negativo: bool) -> Dict[str, float]:
        """
        Retorna as áreas e profundidades das armaduras em relação à face comprimida (y=0).
        """
        if not momento_negativo:
            return {
                "As_tens": self.As_inf, "d_tens": self.d_inf,
                "As_comp": self.As_sup, "d_comp": self.d_sup,
            }
        else:
            # Momento Negativo: tração vai pro topo, compressão vai para base.
            return {
                "As_tens": self.As_sup, "d_tens": self.H_total - self.d_sup,
                "As_comp": self.As_inf, "d_comp": self.H_total - self.d_inf,
            }

    def _momento_estatico(self, x: float, fatias: List, arms: Dict) -> float:
        """
        Calcula o Momento Estático da seção homogenizada em relação à L.N.
        S(x) = S_comp_concreto(x) + S_comp_aço(x) - S_tens_aço(x)
        A raiz da função (onde S(x) == 0) é a Linha Neutra.
        """
        S_c = 0.0

        # Momento estático do concreto comprimido
        for y1, y2, b in fatias:
            if x <= y1:
                continue  # Fatia inteiramente tracionada (fissurada)
            yf = min(x, y2)
            area = b * (yf - y1)
            cg_braco = x - ((y1 + yf) / 2.0)
            S_c += area * cg_braco

        # Momento estático da armadura "comprimida" (se d_comp < x)
        if arms["As_comp"] > 0 and arms["d_comp"] < x:
            S_c += self.n * arms["As_comp"] * (x - arms["d_comp"])

        # Momento estático da armadura tracionada
        S_t = self.n * arms["As_tens"] * (arms["d_tens"] - x)

        return S_c - S_t

    def _bissecao_com_historico(
        self,
        fatias : List,
        arms   : Dict,
        n_iter : int = 6
    ) -> Tuple[float, List, int]:
        """
        Executa a bissecção registrando as primeiras n_iter iterações para exibição
        no memorial de cálculo. Retorna (x_final, historico, total_iteracoes).
        """
        history = []
        a_val, b_val = 1e-4, arms["d_tens"]
        tol = 1e-8
        total_iter = 0

        for i in range(150):
            if (b_val - a_val) / 2.0 <= tol:
                break
            mid = (a_val + b_val) / 2.0
            fa  = self._momento_estatico(a_val, fatias, arms)
            fm  = self._momento_estatico(mid,   fatias, arms)

            if i < n_iter:
                history.append((i + 1, a_val, b_val, mid, fa, fm))

            if fm == 0.0:
                a_val = b_val = mid
                break
            if fa * fm > 0:
                a_val = mid
            else:
                b_val = mid

            total_iter = i + 1

        x_final = (a_val + b_val) / 2.0
        return x_final, history, total_iter

    def resolver(self, momento_kNm: float) -> ResultadoEstadioII:
        """
        Resolve o Estádio II encontrando 'x' por bisseção e calcula J_fiss e Tensões.
        """
        if abs(momento_kNm) < 1e-3 or (self.As_inf == 0 and self.As_sup == 0):
            return ResultadoEstadioII(momento_kNm, False, 0.0, 0.0, 0.0, 0.0)

        is_neg = momento_kNm < 0
        M_abs  = abs(momento_kNm) * 100.0  # kN.m -> kN.cm
        fatias = self._gerar_fatias(is_neg)
        arms   = self._mapear_armaduras(is_neg)

        # ── 1. Encontrar Linha Neutra (x) por Bissecção ────────────────────────
        a_val, b_val = 1e-4, arms["d_tens"]
        tol = 1e-8

        for _ in range(150):
            if (b_val - a_val) / 2.0 <= tol:
                break
            mid = (a_val + b_val) / 2.0
            fa  = self._momento_estatico(a_val, fatias, arms)
            fm  = self._momento_estatico(mid,   fatias, arms)

            if fm == 0.0:
                a_val = b_val = mid
                break
            if fa * fm > 0:
                a_val = mid
            else:
                b_val = mid

        x = (a_val + b_val) / 2.0

        # ── 2. Calcular Inércia Fissurada (J_fiss) ─────────────────────────────
        J = 0.0

        # Concreto Comprimido
        for y1, y2, larg in fatias:
            if x <= y1:
                continue
            yf = min(x, y2)
            hb = yf - y1
            cg = (y1 + yf) / 2.0
            inercia_propria  = (larg * (hb ** 3)) / 12.0
            teorema_steiner  = larg * hb * ((x - cg) ** 2)
            J += inercia_propria + teorema_steiner

        # Aço Comprimido
        if arms["As_comp"] > 0 and arms["d_comp"] < x:
            J += self.n * arms["As_comp"] * ((x - arms["d_comp"]) ** 2)

        # Aço Tracionado
        J += self.n * arms["As_tens"] * ((arms["d_tens"] - x) ** 2)

        # ── 3. Calcular Tensões [MPa] (1 kN/cm² = 10 MPa) ──────────────────────
        # Tensão = n * M * y / J

        # Aço focado em tração
        sigma_tens = self.n * M_abs * (arms["d_tens"] - x) / J * 10.0

        # Aço focado em compressão (pode estar tracionado se d_comp > x)
        sigma_comp = 0.0
        if arms["As_comp"] > 0:
            # Convenção: (-) Compressão, (+) Tração.
            # Se x > d_comp (LN abaixo da barra): a barra está comprimida (negativo)
            # Se x < d_comp (LN acima da barra): a barra está tracionada (positivo)
            sigma_comp = -self.n * M_abs * (x - arms["d_comp"]) / J * 10.0

        # ── 4. Re-mapeamento Fixo (Inf e Sup) ──────────────────────────────────
        if not is_neg:
            sig_inf = sigma_tens
            sig_sup = sigma_comp
        else:
            sig_inf = sigma_comp
            sig_sup = sigma_tens

        return ResultadoEstadioII(
            momento_sd   = momento_kNm,
            is_negativo  = is_neg,
            x_cm         = x,
            Jfiss_cm4    = J,
            sigma_inf_MPa= sig_inf,
            sigma_sup_MPa= sig_sup
        )


# ════════════════════════════════════════════════════════════════════════════════
# 3. CALCULADORA PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════════

class CalculadoraFlexaoFadiga:
    """
    Classe orquestradora para verificação da fadiga na flexão.
    Calcula os dois estados de tensão (M1 e M2) e faz a verificação final.

    Parâmetros adicionais (verificar_fadiga):
        eta               : Fator de aproveitamento para correção da armadura.
                            Padrão = 1.0. Quando η < 1, exige mais aço; quando η > 1,
                            pode exigir menos. A fórmula de correção é:
                              As_corr = As_orig × k / η  (onde k = Δσ / Δf_fad,sd)
        delta_f_fad_sd_inf: Resistência à fadiga do aço de projeto para a
                            armadura INFERIOR [MPa]. Ex: 175 MPa (CA-50, ø ≤ 22mm).
        delta_f_fad_sd_sup: Resistência à fadiga do aço de projeto para a
                            armadura SUPERIOR [MPa]. Idem.
    """

    def __init__(self, delta_f_fad_sd: float = 175.0):
        """
        Args:
            delta_f_fad_sd: Valor padrão de resistência à fadiga usado quando
                            delta_f_fad_sd_inf / delta_f_fad_sd_sup não forem
                            especificados em verificar_fadiga [MPa].
        """
        self.delta_f_fad_default : float                   = delta_f_fad_sd
        self.ultimo_resultado    : Optional[ResultadoFadiga]  = None
        self.ultimo_motor        : Optional[MotorEstadioII]   = None

    # ─────────────────────────────────────────────────────────────────────────
    # CÁLCULO PRINCIPAL
    # ─────────────────────────────────────────────────────────────────────────

    def verificar_fadiga(
        self,
        dados_secao         : Dict,
        M_1                 : float,
        M_2                 : float,
        n_eq                : float,
        As_inf              : float,
        d_inf               : float,
        As_sup              : float = 0.0,
        d_sup               : float = 0.0,
        h_laje              : float = 0.0,
        b_laje              : float = 0.0,
        eta                 : float = 1.0,
        delta_f_fad_sd_inf  : Optional[float] = None,
        delta_f_fad_sd_sup  : Optional[float] = None,
    ) -> ResultadoFadiga:
        """
        Executa o cálculo para dois momentos e extrai o coeficiente de fadiga.

        Args:
            dados_secao        : Dicionário com geometria da seção.
            M_1                : Momento máximo de fadiga (estado 1) [kN.m].
            M_2                : Momento mínimo de fadiga (estado 2) [kN.m].
            n_eq               : Relação modular de homogenização (Es / Ec).
            As_inf             : Área da armadura inferior [cm²].
            d_inf              : Altura útil da armadura inferior [cm].
            As_sup             : Área da armadura superior [cm²] (padrão 0).
            d_sup              : Cobrimento + raio – distância da face sup. à As' [cm].
            h_laje             : Espessura da laje colaborante [cm] (padrão 0).
            b_laje             : Largura da laje colaborante [cm] (padrão 0).
            eta                : Fator de aproveitamento η para correção da armadura (padrão 1.0).
            delta_f_fad_sd_inf : Resistência à fadiga da armadura INFERIOR [MPa].
                                 Se None, usa o valor padrão do construtor.
            delta_f_fad_sd_sup : Resistência à fadiga da armadura SUPERIOR [MPa].
                                 Se None, usa o valor padrão do construtor.
        Returns:
            ResultadoFadiga com todos os resultados da verificação.
        """
        # Resolve limites de fadiga, usando o padrão caso não informados
        dff_inf = delta_f_fad_sd_inf if delta_f_fad_sd_inf is not None else self.delta_f_fad_default
        dff_sup = delta_f_fad_sd_sup if delta_f_fad_sd_sup is not None else self.delta_f_fad_default

        motor = MotorEstadioII(
            dados_secao, n_eq, As_inf, d_inf, As_sup, d_sup, h_laje, b_laje
        )
        self.ultimo_motor = motor

        res_m1 = motor.resolver(M_1)
        res_m2 = motor.resolver(M_2)

        # ── Variações de tensão ──────────────────────────────────────────────
        # |σ_1 − σ_2| → usa o valor algébrico para capturar a amplitude total.
        # Ex: σ_1 = +150 MPa, σ_2 = −20 MPa → Δσ = |150 − (−20)| = 170 MPa
        delta_inf = abs(res_m1.sigma_inf_MPa - res_m2.sigma_inf_MPa)
        delta_sup = abs(res_m1.sigma_sup_MPa - res_m2.sigma_sup_MPa)

        # ── Coeficientes de utilização à fadiga ──────────────────────────────
        k_inf = (delta_inf / dff_inf) if As_inf > 0 else 0.0
        k_sup = (delta_sup / dff_sup) if As_sup > 0 else 0.0

        # ── Correção das armaduras (quando k > 1) ────────────────────────────
        # Fundamentação: para uma seção fissurada, a variação de tensão é
        # aproximadamente inversamente proporcional à área de aço:
        #   Δσ ≈ M / (As · j · d)   →   As_corr = As_orig × (Δσ / Δf_fad,sd) / η
        # Portanto: As_corr = As_orig × k / η
        if As_inf > 0:
            if k_inf <= 1.0:
                as_inf_corrigida: Union[str, float] = "Não houve necessidade de correção"
            else:
                as_inf_corrigida = round(As_inf * k_inf / eta, 2)
        else:
            as_inf_corrigida = "Sem armadura inferior"

        if As_sup > 0:
            if k_sup <= 1.0:
                as_sup_corrigida: Union[str, float] = "Não houve necessidade de correção"
            else:
                as_sup_corrigida = round(As_sup * k_sup / eta, 2)
        else:
            as_sup_corrigida = "Sem armadura superior"

        resultado = ResultadoFadiga(
            res_M1              = res_m1,
            res_M2              = res_m2,
            eta                 = eta,
            delta_f_fad_sd_inf  = dff_inf,
            delta_f_fad_sd_sup  = dff_sup,
            delta_sigma_inf_MPa = delta_inf,
            k_fad_inf           = k_inf,
            verifica_inf        = (k_inf <= 1.0),
            as_inf_corrigida    = as_inf_corrigida,
            delta_sigma_sup_MPa = delta_sup,
            k_fad_sup           = k_sup,
            verifica_sup        = (k_sup <= 1.0),
            as_sup_corrigida    = as_sup_corrigida,
        )
        self.ultimo_resultado = resultado
        return resultado

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS INTERNOS DO MEMORIAL
    # ─────────────────────────────────────────────────────────────────────────

    def _detalhar_estado(
        self,
        res   : ResultadoEstadioII,
        motor : MotorEstadioII
    ) -> Dict:
        """
        Recomputa todos os valores intermediários de um estado de tensão
        para uso exclusivo no memorial de cálculo.
        Retorna um dicionário com fatias comprimidas, contribuições de inércia,
        contribuições de aço, bisseção e tensões.
        """
        is_neg = res.is_negativo
        fatias = motor._gerar_fatias(is_neg)
        arms   = motor._mapear_armaduras(is_neg)
        x      = res.x_cm
        M_abs  = abs(res.momento_sd) * 100.0  # kN.m → kN.cm

        # ── Bissecção com histórico (primeiras 6 iterações) ──────────────────
        _, hist_bis, n_iter_total = motor._bissecao_com_historico(fatias, arms, n_iter=6)

        # ── Fatias de concreto comprimidas ───────────────────────────────────
        fatias_det = []
        S_conc  = 0.0
        J_conc  = 0.0
        for y1, y2, b in fatias:
            if x <= y1:
                continue
            yf    = min(x, y2)
            hb    = yf - y1
            area  = b * hb
            cg    = (y1 + yf) / 2.0
            braco = x - cg
            S_f   = area * braco
            Ip    = b * hb ** 3 / 12.0
            St    = area * braco ** 2
            Jf    = Ip + St
            S_conc += S_f
            J_conc += Jf
            fatias_det.append({
                "y1": y1, "y2": yf, "b": b, "hb": hb,
                "area": area, "cg": cg, "braco": braco,
                "S": S_f, "Ip": Ip, "St": St, "J": Jf
            })

        # ── Contribuição do aço comprimido (As') ─────────────────────────────
        J_aco_comp = 0.0
        S_aco_comp = 0.0
        aco_comp_det = {}
        if arms["As_comp"] > 0 and arms["d_comp"] < x:
            braco_ac  = x - arms["d_comp"]
            J_aco_comp = motor.n * arms["As_comp"] * braco_ac ** 2
            S_aco_comp = motor.n * arms["As_comp"] * braco_ac
            aco_comp_det = {
                "n": motor.n, "As": arms["As_comp"], "d": arms["d_comp"],
                "braco": braco_ac, "J": J_aco_comp, "S": S_aco_comp
            }

        # ── Contribuição do aço tracionado (As) ──────────────────────────────
        braco_at   = arms["d_tens"] - x
        J_aco_tens = motor.n * arms["As_tens"] * braco_at ** 2
        S_aco_tens = motor.n * arms["As_tens"] * braco_at
        aco_tens_det = {
            "n": motor.n, "As": arms["As_tens"], "d": arms["d_tens"],
            "braco": braco_at, "J": J_aco_tens, "S": S_aco_tens
        }

        J_total = J_conc + J_aco_comp + J_aco_tens

        # ── Tensões ──────────────────────────────────────────────────────────
        sigma_tens = motor.n * M_abs * braco_at / J_total * 10.0
        sigma_comp = 0.0
        if arms["As_comp"] > 0:
            sigma_comp = -motor.n * M_abs * (x - arms["d_comp"]) / J_total * 10.0

        return {
            "is_neg"       : is_neg,
            "fatias_bruta" : fatias,
            "arms"         : arms,
            "x"            : x,
            "M_abs_kNcm"   : M_abs,
            "fatias_det"   : fatias_det,
            "S_conc"       : S_conc,
            "J_conc"       : J_conc,
            "aco_comp_det" : aco_comp_det,
            "J_aco_comp"   : J_aco_comp,
            "S_aco_comp"   : S_aco_comp,
            "aco_tens_det" : aco_tens_det,
            "J_aco_tens"   : J_aco_tens,
            "S_aco_tens"   : S_aco_tens,
            "J_total"      : J_total,
            "sigma_tens"   : sigma_tens,
            "sigma_comp"   : sigma_comp,
            "hist_bis"     : hist_bis,
            "n_iter_total" : n_iter_total,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # GERAÇÃO DE RELATÓRIOS (TEXTO E HTML)
    # ─────────────────────────────────────────────────────────────────────────

    def obter_relatorio_resumido(self) -> Tuple[str, str]:
        """
        Gera o memorial de cálculo completo e detalhado (Texto e HTML Tema Escuro).
        Exibe TODAS as etapas intermediárias: geometria, fatias, bissecção,
        inércias individuais, tensões e verificação de fadiga.
        """
        if not self.ultimo_resultado or not self.ultimo_motor:
            msg = "Nenhum dimensionamento de fadiga realizado ainda."
            return msg, f"<p>{msg}</p>"

        r  = self.ultimo_resultado
        m  = self.ultimo_motor
        r1, r2 = r.res_M1, r.res_M2

        # Recomputa detalhes intermediários para ambos os estados
        det1 = self._detalhar_estado(r1, m)
        det2 = self._detalhar_estado(r2, m)

        # Nomes das faces dependendo do sinal do momento
        def face_comp(is_neg): return "INFERIOR (base)" if is_neg else "SUPERIOR (topo)"
        def face_trac(is_neg): return "SUPERIOR (topo)" if is_neg else "INFERIOR (base)"

        # ─────────────────────────────────────────────────────────────────────
        #  RELATÓRIO TEXTO
        # ─────────────────────────────────────────────────────────────────────
        SEP_D = "=" * 80
        SEP_S = "-" * 80
        SEP_M = "-" * 60
        SEP_P = "·" * 60

        txt = []
        txt.append(SEP_D)
        txt.append("MEMORIAL DE CÁLCULO – VERIFICAÇÃO À FADIGA NA FLEXÃO")
        txt.append("Resistência das Estruturas de Concreto – NBR 6118:2014")
        txt.append("Seção Fissurada (Estádio II) – Motor Numérico por Fatias + Bissecção")
        txt.append(SEP_D)

        # ═══════════════════════════════════════════════════════════════════════
        # SEÇÃO 1: DADOS DE ENTRADA
        # ═══════════════════════════════════════════════════════════════════════
        txt.append("")
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 1 – DADOS DE ENTRADA                                │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  1.1. GEOMETRIA DA SEÇÃO TRANSVERSAL")
        txt.append("  " + SEP_M)
        txt.append(f"  Tipo de Seção          : {m.dados.get('Tipo')}")
        txt.append(f"  Altura Total (H_total) : {m.H_total:.2f} cm")

        tipo = m.dados.get("Tipo", "")
        if tipo == TipoSecao.RETANGULAR.value:
            bw = float(m.dados.get("bw", m.dados.get("b", 0)))
            txt.append(f"  Largura da Alma (bw)   : {bw:.2f} cm")
        elif tipo == TipoSecao.T.value:
            txt.append(f"  Largura da Alma   (bw) : {m.dados['bw']:.1f} cm")
            txt.append(f"  Altura da Viga    (h)  : {m.dados['h']:.1f} cm")
            txt.append(f"  Largura da Mesa   (bf) : {m.dados['bf']:.1f} cm")
            txt.append(f"  Espessura da Mesa (hf) : {m.dados['hf']:.1f} cm")
        elif tipo == TipoSecao.I.value:
            txt.append(f"  Largura da Alma   (bw)  : {m.dados['bw']:.1f} cm")
            txt.append(f"  Altura da Viga    (h)   : {m.dados['h']:.1f} cm")
            txt.append(f"  Mesa Sup. (btf × hft)   : {m.dados['btf']:.1f} × {m.dados['hft']:.1f} cm")
            txt.append(f"  Mesa Inf. (bfb × hfb)   : {m.dados['bfb']:.1f} × {m.dados['hfb']:.1f} cm")
        if m.h_laje > 0:
            txt.append(f"  Laje Colaborante (h_L)  : {m.h_laje:.2f} cm  |  b_L = {m.b_laje:.2f} cm")
        txt.append("")
        txt.append("  1.2. MATERIAIS E RELAÇÃO MODULAR")
        txt.append("  " + SEP_M)
        txt.append(f"  Relação Modular n = Es/Ec : {m.n:.2f}")
        txt.append("  (O aço é substituído por concreto equivalente de área n×As)")
        txt.append("")
        txt.append("  1.3. ARMADURAS DE FLEXÃO")
        txt.append("  " + SEP_M)
        txt.append(f"  Armadura Inferior (As)    : {m.As_inf:.2f} cm²")
        txt.append(f"  Altura útil inf.  (d_inf) : {m.d_inf:.2f} cm")
        txt.append(f"  Cobrimento efetivo inf.   : {m.H_total - m.d_inf:.2f} cm")
        if m.As_sup > 0:
            txt.append(f"  Armadura Superior (As')   : {m.As_sup:.2f} cm²")
            txt.append(f"  Altura útil sup.  (d_sup) : {m.d_sup:.2f} cm")
        else:
            txt.append("  Armadura Superior (As')   : Não existe (seção simples)")
        txt.append("")
        txt.append("  1.4. SOLICITAÇÕES DE FADIGA (MOMENTOS FLETORES DE PROJETO)")
        txt.append("  " + SEP_M)
        txt.append(f"  Momento máximo   Msd,1 = {r1.momento_sd:+.2f} kN.m  ← Estado 1")
        txt.append(f"  Momento mínimo   Msd,2 = {r2.momento_sd:+.2f} kN.m  ← Estado 2")
        amp = abs(r1.momento_sd - r2.momento_sd)
        txt.append(f"  Amplitude de momento   = |Msd,1 − Msd,2| = {amp:.2f} kN.m")
        txt.append("")
        txt.append("  1.5. PARÂMETROS DE FADIGA")
        txt.append("  " + SEP_M)
        txt.append(f"  Fator de aproveitamento η       : {r.eta:.4f}")
        txt.append(f"  Δf_fad,sd (armadura INFERIOR)   : {r.delta_f_fad_sd_inf:.2f} MPa")
        txt.append(f"  Δf_fad,sd (armadura SUPERIOR)   : {r.delta_f_fad_sd_sup:.2f} MPa")
        txt.append("  Nota: Δf_fad,sd é a resistência à fadiga de projeto do aço")
        txt.append("  conforme NBR 6118:2014, Tabela 23.3.")
        txt.append("")

        # ═══════════════════════════════════════════════════════════════════════
        # SEÇÃO 2: PRÉ-PROCESSAMENTO – FATIAS
        # ═══════════════════════════════════════════════════════════════════════
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 2 – DISCRETIZAÇÃO DA SEÇÃO EM FATIAS RETANGULARES  │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  O motor numérico representa a seção transversal como uma lista")
        txt.append("  de retângulos (fatias), cada um definido por:")
        txt.append("    • y_início [cm] – posição da borda superior da fatia")
        txt.append("    • y_fim    [cm] – posição da borda inferior da fatia")
        txt.append("    • largura  [cm] – largura da fatia")
        txt.append("  A origem (y = 0) é fixada na FACE MAIS COMPRIMIDA.")
        txt.append("")

        # Para momento positivo usa det1 (mais comum para ilustrar)
        fatias_ref = det1["fatias_bruta"]
        txt.append(f"  Para Msd,1 = {r1.momento_sd:+.2f} kN.m:")
        txt.append(f"  Face comprimida: {face_comp(det1['is_neg'])}")
        txt.append("")
        txt.append(f"  {'Nº':<4} {'y_inic [cm]':>12} {'y_fim [cm]':>11} {'Larg [cm]':>10}")
        txt.append("  " + "-" * 42)
        for i, (y1, y2, b) in enumerate(fatias_ref, 1):
            txt.append(f"  {i:<4} {y1:>12.2f} {y2:>11.2f} {b:>10.2f}")
        txt.append("")
        if det1["is_neg"] != det2["is_neg"]:
            fatias_ref2 = det2["fatias_bruta"]
            txt.append(f"  Para Msd,2 = {r2.momento_sd:+.2f} kN.m (sinal INVERTIDO → seção rotacionada):")
            txt.append(f"  Face comprimida: {face_comp(det2['is_neg'])}")
            txt.append("")
            txt.append(f"  {'Nº':<4} {'y_inic [cm]':>12} {'y_fim [cm]':>11} {'Larg [cm]':>10}")
            txt.append("  " + "-" * 42)
            for i, (y1, y2, b) in enumerate(fatias_ref2, 1):
                txt.append(f"  {i:<4} {y1:>12.2f} {y2:>11.2f} {b:>10.2f}")
        txt.append("")

        # ═══════════════════════════════════════════════════════════════════════
        # SEÇÃO 3 e 4: ESTÁDIO II – ESTADO 1 e 2
        # ═══════════════════════════════════════════════════════════════════════
        for idx_est, (res, det) in enumerate([(r1, det1), (r2, det2)], start=1):
            sec_num = 2 + idx_est  # Seção 3 e 4
            txt.append(SEP_S)
            txt.append(f"┌─────────────────────────────────────────────────────────────┐")
            txt.append(f"│   SEÇÃO {sec_num} – ESTÁDIO II: ESTADO DE TENSÕES {idx_est}                │")
            txt.append(f"│   Msd,{idx_est} = {res.momento_sd:+.2f} kN.m".ljust(64) + "│")
            txt.append(f"└─────────────────────────────────────────────────────────────┘")
            txt.append("")
            txt.append(f"  Face comprimida (y = 0): {face_comp(det['is_neg'])}")
            txt.append(f"  Face tracionada         : {face_trac(det['is_neg'])}")
            txt.append(f"  Armadura de tração      : As_tens = {det['arms']['As_tens']:.2f} cm²  "
                       f"(d_tens = {det['arms']['d_tens']:.2f} cm)")
            if det["arms"]["As_comp"] > 0:
                txt.append(f"  Armadura de compressão  : As_comp = {det['arms']['As_comp']:.2f} cm²  "
                           f"(d_comp = {det['arms']['d_comp']:.2f} cm)")
            txt.append("")

            # ── 3.1 / 4.1: Equação de equilíbrio ───────────────────────────
            txt.append(f"  {sec_num}.1. DETERMINAÇÃO DA LINHA NEUTRA (x) – MÉTODO DA BISSECÇÃO")
            txt.append("  " + SEP_M)
            txt.append("")
            txt.append("  Princípio: na Teoria da Seção Fissurada (Estádio II), a linha neutra")
            txt.append("  é localizada onde o MOMENTO ESTÁTICO da seção homogenizada é NULO:")
            txt.append("")
            txt.append("         S(x) = S_concreto_comprimido(x) + n·As_comp·(x − d_comp)")
            txt.append("              − n·As_tens·(d_tens − x)  =  0")
            txt.append("")
            txt.append("  Equação expandida por fatias:")
            txt.append("  Σ [ b_i · h_i · (x − ȳ_i) ]  +  n·As_comp·(x − d_comp)")
            txt.append("                               −  n·As_tens·(d_tens − x) = 0")
            txt.append("")
            txt.append("  Dados do problema:")
            txt.append(f"    n            = {m.n:.4f}")
            txt.append(f"    As_tens      = {det['arms']['As_tens']:.2f} cm²  "
                       f"|  d_tens = {det['arms']['d_tens']:.2f} cm")
            if det["arms"]["As_comp"] > 0:
                txt.append(f"    As_comp      = {det['arms']['As_comp']:.2f} cm²  "
                           f"|  d_comp = {det['arms']['d_comp']:.2f} cm")
            txt.append("")
            txt.append("  Iterações da Bissecção (primeiras iterações):")
            txt.append(f"  Intervalo inicial: [a = 0,0001 cm, b = {det['arms']['d_tens']:.4f} cm]")
            txt.append("")
            txt.append(f"  {'Iter':>4}  {'a [cm]':>10}  {'b [cm]':>10}  {'x_mid [cm]':>12}  "
                       f"{'S(a) [cm³]':>14}  {'S(x_mid) [cm³]':>16}")
            txt.append("  " + "-" * 75)
            for it in det["hist_bis"]:
                n_it, a_it, b_it, mid_it, fa_it, fm_it = it
                txt.append(f"  {n_it:>4}  {a_it:>10.4f}  {b_it:>10.4f}  {mid_it:>12.4f}  "
                           f"{fa_it:>14.4f}  {fm_it:>16.4f}")
            txt.append(f"  ... (convergência atingida em {det['n_iter_total']} iterações, tol = 1×10⁻⁸ cm)")
            txt.append("")
            txt.append(f"  ►  x = {det['x']:.4f} cm  (medido da face comprimida: {face_comp(det['is_neg'])})")
            txt.append("")

            # ── 3.2 / 4.2: Inércia Fissurada ────────────────────────────────
            txt.append(f"  {sec_num}.2. INÉRCIA FISSURADA (J_fiss)")
            txt.append("  " + SEP_M)
            txt.append("")
            txt.append("  Fórmula geral (Teorema de Steiner) para cada fatia de concreto i:")
            txt.append("    J_concreto,i = (b_i · h_i³)/12  +  b_i · h_i · (x − ȳ_i)²")
            txt.append("  Para o aço (homogeneizado):")
            txt.append("    J_aço        = n · As · (d − x)²")
            txt.append("")
            txt.append("  Contribuições das FATIAS de CONCRETO COMPRIMIDAS:")
            txt.append(f"  {'Fatia':<6} {'y1':>7} {'y2':>7} {'b':>7} {'h':>7} "
                       f"{'Área':>10} {'ȳ':>7} {'braço':>8} {'I_prop':>14} {'Steiner':>14} {'J_fatia':>14}")
            txt.append("  " + "─" * 110)
            for i, fd in enumerate(det["fatias_det"], 1):
                txt.append(
                    f"  {i:<6} {fd['y1']:>7.3f} {fd['y2']:>7.3f} {fd['b']:>7.2f} {fd['hb']:>7.3f} "
                    f"{fd['area']:>10.3f} {fd['cg']:>7.3f} {fd['braco']:>8.3f} "
                    f"{fd['Ip']:>14.2f} {fd['St']:>14.2f} {fd['J']:>14.2f}"
                )
            txt.append("  " + "─" * 110)
            txt.append(f"  {'TOTAL':>6} {'':>7} {'':>7} {'':>7} {'':>7} {'':>10} {'':>7} {'':>8} "
                       f"{'':>14} {'':>14} {det['J_conc']:>14.2f}  ← J_concreto")
            txt.append("")

            if det["aco_comp_det"]:
                acd = det["aco_comp_det"]
                txt.append("  Contribuição do AÇO COMPRIMIDO (As'):")
                txt.append(f"    J_ac = n × As_comp × (x − d_comp)²")
                txt.append(f"         = {acd['n']:.4f} × {acd['As']:.4f} × ({det['x']:.4f} − {acd['d']:.4f})²")
                txt.append(f"         = {acd['n']:.4f} × {acd['As']:.4f} × {acd['braco']:.4f}²")
                txt.append(f"         = {acd['n']:.4f} × {acd['As']:.4f} × {acd['braco']**2:.4f}")
                txt.append(f"         = {det['J_aco_comp']:.4f} cm⁴")
                txt.append("")

            atd = det["aco_tens_det"]
            txt.append("  Contribuição do AÇO TRACIONADO (As):")
            txt.append(f"    J_at = n × As_tens × (d_tens − x)²")
            txt.append(f"         = {atd['n']:.4f} × {atd['As']:.4f} × ({atd['d']:.4f} − {det['x']:.4f})²")
            txt.append(f"         = {atd['n']:.4f} × {atd['As']:.4f} × {atd['braco']:.4f}²")
            txt.append(f"         = {atd['n']:.4f} × {atd['As']:.4f} × {atd['braco']**2:.4f}")
            txt.append(f"         = {det['J_aco_tens']:.4f} cm⁴")
            txt.append("")
            txt.append("  TOTAL – Inércia Fissurada Homogenizada:")
            txt.append(f"    J_fiss = J_concreto + J_aço_comp + J_aço_tens")
            J_ac = det['J_aco_comp']
            txt.append(f"           = {det['J_conc']:.4f}  +  {J_ac:.4f}  +  {det['J_aco_tens']:.4f}")
            txt.append(f"           = {det['J_total']:.4f} cm⁴")
            txt.append(f"           = {det['J_total']/1e8:.6f} m⁴")
            txt.append("")
            txt.append(f"  ►  J_fiss = {det['J_total']:.2f} cm⁴  =  {det['J_total']/1e8:.6f} m⁴")
            txt.append("")

            # ── 3.3 / 4.3: Tensões ──────────────────────────────────────────
            txt.append(f"  {sec_num}.3. CÁLCULO DAS TENSÕES NAS ARMADURAS (σ_s)")
            txt.append("  " + SEP_M)
            txt.append("")
            txt.append("  Fórmula geral (seção fissurada homogenizada, Teoria Elástica Linear):")
            txt.append("    σ_s = n · M_abs · y_rel / J_fiss")
            txt.append("  onde:")
            txt.append("    y_rel = distância da armadura à Linha Neutra [cm]")
            txt.append(f"    n     = {m.n:.4f}  (relação modular)")
            txt.append(f"    M_abs = |Msd| = |{res.momento_sd:.2f}| kN.m × 100 = {det['M_abs_kNcm']:.2f} kN.cm")
            txt.append(f"    J_fiss= {det['J_total']:.2f} cm⁴")
            txt.append("  Obs.: σ [MPa] = σ [kN/cm²] × 10.0  (1 kN/cm² = 10 MPa)")
            txt.append("")
            txt.append("  ── Armadura TRACIONADA ──────────────────────────────────────────")
            txt.append(f"    y_rel_tens = d_tens − x = {atd['d']:.4f} − {det['x']:.4f} = {atd['braco']:.4f} cm")
            txt.append(f"    σ_tens = n × M_abs × y_rel_tens / J_fiss")
            txt.append(f"           = {m.n:.4f} × {det['M_abs_kNcm']:.4f} × {atd['braco']:.4f} / {det['J_total']:.4f}")
            sigma_tens_kN = m.n * det['M_abs_kNcm'] * atd['braco'] / det['J_total']
            txt.append(f"           = {sigma_tens_kN:.6f} kN/cm²")
            txt.append(f"           = {sigma_tens_kN:.6f} × 10 = {sigma_tens_kN*10:.4f} MPa  (tração: positivo)")
            txt.append("")
            if det["aco_comp_det"]:
                acd = det["aco_comp_det"]
                txt.append("  ── Armadura de COMPRESSÃO (As') ────────────────────────────────")
                txt.append(f"    y_rel_comp = x − d_comp = {det['x']:.4f} − {acd['d']:.4f} = {acd['braco']:.4f} cm")
                txt.append(f"    σ_comp = −n × M_abs × y_rel_comp / J_fiss")
                txt.append(f"           = −{m.n:.4f} × {det['M_abs_kNcm']:.4f} × {acd['braco']:.4f} / {det['J_total']:.4f}")
                sigma_comp_kN = -m.n * det['M_abs_kNcm'] * acd['braco'] / det['J_total']
                txt.append(f"           = {sigma_comp_kN:.6f} kN/cm²")
                txt.append(f"           = {sigma_comp_kN:.6f} × 10 = {sigma_comp_kN*10:.4f} MPa  (compressão: negativo)")
                txt.append("")

            txt.append("  ── Remapeamento para referencial FIXO (Inferior / Superior) ────")
            if not det["is_neg"]:
                txt.append(f"    Momento positivo → As_inf = armadura de TRAÇÃO")
                txt.append(f"    σ_inf = {res.sigma_inf_MPa:+.4f} MPa  (armadura inferior)")
                txt.append(f"    σ_sup = {res.sigma_sup_MPa:+.4f} MPa  (armadura superior)")
            else:
                txt.append(f"    Momento negativo → As_sup = armadura de TRAÇÃO")
                txt.append(f"    σ_inf = {res.sigma_inf_MPa:+.4f} MPa  (armadura inferior – comprimida)")
                txt.append(f"    σ_sup = {res.sigma_sup_MPa:+.4f} MPa  (armadura superior – tracionada)")
            txt.append("")
            txt.append(f"  ►  σ_inf,{idx_est} = {res.sigma_inf_MPa:+.4f} MPa")
            txt.append(f"  ►  σ_sup,{idx_est} = {res.sigma_sup_MPa:+.4f} MPa")
            txt.append("")

        # ═══════════════════════════════════════════════════════════════════════
        # SEÇÃO 5: VERIFICAÇÃO À FADIGA
        # ═══════════════════════════════════════════════════════════════════════
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 5 – VERIFICAÇÃO À FADIGA  (NBR 6118:2014)          │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Condição de verificação (NBR 6118, item 23.5.4):")
        txt.append("    Δσ_s,d  ≤  Δf_fad,s,d")
        txt.append("  onde:")
        txt.append("    Δσ_s,d   = variação de tensão na armadura = |σ_s,1 − σ_s,2|")
        txt.append("    Δf_fad,s,d = resistência à fadiga de projeto do aço")
        txt.append("")
        txt.append("  Coeficiente de utilização à fadiga:")
        txt.append("    k_fad = Δσ_s,d / Δf_fad,s,d   →   deve ser ≤ 1,0")
        txt.append("")
        txt.append("  Resumo das tensões calculadas:")
        txt.append(f"  {'Armadura':<22} {'σ_s,1 [MPa]':>14} {'σ_s,2 [MPa]':>14} {'Δσ [MPa]':>12} {'Δf_fad [MPa]':>14}")
        txt.append("  " + "─" * 80)
        if m.As_inf > 0:
            txt.append(
                f"  {'Inferior (As)':.<22} {r1.sigma_inf_MPa:>+14.4f} {r2.sigma_inf_MPa:>+14.4f}"
                f" {r.delta_sigma_inf_MPa:>12.4f} {r.delta_f_fad_sd_inf:>14.2f}"
            )
        if m.As_sup > 0:
            label_sup = "Superior (As')"
            txt.append(
                f"  {label_sup:.<22} {r1.sigma_sup_MPa:>+14.4f} {r2.sigma_sup_MPa:>+14.4f}"
                f" {r.delta_sigma_sup_MPa:>12.4f} {r.delta_f_fad_sd_sup:>14.2f}"
            )
        txt.append("")

        if m.As_inf > 0:
            txt.append("  5.1. ARMADURA INFERIOR (As)")
            txt.append("  " + SEP_M)
            txt.append(f"    Δσ_s,d,inf = |σ_inf,1 − σ_inf,2|")
            txt.append(f"               = |({r1.sigma_inf_MPa:+.4f}) − ({r2.sigma_inf_MPa:+.4f})|")
            txt.append(f"               = {r.delta_sigma_inf_MPa:.4f} MPa")
            txt.append("")
            txt.append(f"    k_fad,inf  = Δσ_s,d,inf / Δf_fad,sd,inf")
            txt.append(f"               = {r.delta_sigma_inf_MPa:.4f} / {r.delta_f_fad_sd_inf:.2f}")
            txt.append(f"               = {r.k_fad_inf:.6f}")
            txt.append("")
            txt.append(f"    Verificação: k_fad,inf = {r.k_fad_inf:.4f}  {'≤ 1,0 ✓  VERIFICAÇÃO ATENDIDA' if r.verifica_inf else '> 1,0 ✗  VERIFICAÇÃO NÃO ATENDIDA'}")
            txt.append("")
            if not r.verifica_inf:
                txt.append("    ► CORREÇÃO DA ARMADURA INFERIOR:")
                txt.append("    Quando k > 1, a área de aço deve ser ampliada.")
                txt.append("    Fundamento: Δσ ∝ 1/As (relação inversamente proporcional)")
                txt.append("    Para que Δσ_corr = Δf_fad,sd,inf, a nova área deve ser:")
                txt.append("")
                txt.append("       As,inf,corr = As,inf,original × k_fad,inf / η")
                txt.append(f"                   = {m.As_inf:.4f} × {r.k_fad_inf:.6f} / {r.eta:.4f}")
                txt.append(f"                   = {r.as_inf_corrigida:.4f} cm²")
                txt.append("")
            else:
                txt.append(f"    Correção de armadura : Não houve necessidade de correção")
            txt.append(f"    As_inf_corrigida     : {r.as_inf_corrigida}")
            txt.append("")

        if m.As_sup > 0:
            txt.append("  5.2. ARMADURA SUPERIOR (As')")
            txt.append("  " + SEP_M)
            txt.append(f"    Δσ_s,d,sup = |σ_sup,1 − σ_sup,2|")
            txt.append(f"               = |({r1.sigma_sup_MPa:+.4f}) − ({r2.sigma_sup_MPa:+.4f})|")
            txt.append(f"               = {r.delta_sigma_sup_MPa:.4f} MPa")
            txt.append("")
            txt.append(f"    k_fad,sup  = Δσ_s,d,sup / Δf_fad,sd,sup")
            txt.append(f"               = {r.delta_sigma_sup_MPa:.4f} / {r.delta_f_fad_sd_sup:.2f}")
            txt.append(f"               = {r.k_fad_sup:.6f}")
            txt.append("")
            txt.append(f"    Verificação: k_fad,sup = {r.k_fad_sup:.4f}  {'≤ 1,0 ✓  VERIFICAÇÃO ATENDIDA' if r.verifica_sup else '> 1,0 ✗  VERIFICAÇÃO NÃO ATENDIDA'}")
            txt.append("")
            if not r.verifica_sup:
                txt.append("    ► CORREÇÃO DA ARMADURA SUPERIOR:")
                txt.append("       As,sup,corr = As,sup,original × k_fad,sup / η")
                txt.append(f"                   = {m.As_sup:.4f} × {r.k_fad_sup:.6f} / {r.eta:.4f}")
                txt.append(f"                   = {r.as_sup_corrigida:.4f} cm²")
                txt.append("")
            else:
                txt.append(f"    Correção de armadura : Não houve necessidade de correção")
            txt.append(f"    As_sup_corrigida     : {r.as_sup_corrigida}")
            txt.append("")

        # ═══════════════════════════════════════════════════════════════════════
        # SEÇÃO 6: SÍNTESE FINAL
        # ═══════════════════════════════════════════════════════════════════════
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 6 – SÍNTESE FINAL DOS RESULTADOS                   │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append(f"  {'GRANDEZA':<45} {'ESTADO 1':>12} {'ESTADO 2':>12}")
        txt.append("  " + "─" * 72)
        txt.append(f"  {'Momento Msd [kN.m]':<45} {r1.momento_sd:>+12.2f} {r2.momento_sd:>+12.2f}")
        txt.append(f"  {'Linha Neutra x [cm]':<45} {r1.x_cm:>12.4f} {r2.x_cm:>12.4f}")
        txt.append(f"  {'Inércia J_fiss [cm⁴]':<45} {r1.Jfiss_cm4:>12.2f} {r2.Jfiss_cm4:>12.2f}")
        if m.As_inf > 0:
            txt.append(f"  {'σ_s,inf  (armadura inferior) [MPa]':<45} {r1.sigma_inf_MPa:>+12.4f} {r2.sigma_inf_MPa:>+12.4f}")
        if m.As_sup > 0:
            txt.append(f"  {'σ_s,sup  (armadura superior) [MPa]':<45} {r1.sigma_sup_MPa:>+12.4f} {r2.sigma_sup_MPa:>+12.4f}")
        txt.append("")
        txt.append(f"  {'VERIFICAÇÃO À FADIGA':<45} {'k_fad':>12} {'STATUS':>12}")
        txt.append("  " + "─" * 72)
        if m.As_inf > 0:
            st = "APROVADO ✓" if r.verifica_inf else "REPROVADO ✗"
            txt.append(f"  {'Armadura Inferior (Δf_fad=' + str(r.delta_f_fad_sd_inf) + ' MPa)':<45} {r.k_fad_inf:>12.4f} {st:>12}")
        if m.As_sup > 0:
            st = "APROVADO ✓" if r.verifica_sup else "REPROVADO ✗"
            txt.append(f"  {'Armadura Superior (Δf_fad=' + str(r.delta_f_fad_sd_sup) + ' MPa)':<45} {r.k_fad_sup:>12.4f} {st:>12}")
        txt.append("")
        txt.append(f"  {'ARMADURA CORRIGIDA':<45} {'VALOR':>24}")
        txt.append("  " + "─" * 72)
        if m.As_inf > 0:
            txt.append(f"  {'As_inf_corrigida [cm²]':<45} {str(r.as_inf_corrigida):>24}")
        if m.As_sup > 0:
            txt.append(f"  {'As_sup_corrigida [cm²]':<45} {str(r.as_sup_corrigida):>24}")
        txt.append("")
        txt.append(SEP_D)
        txt.append("FIM DO MEMORIAL DE CÁLCULO")
        txt.append(SEP_D)

        texto_plano = "\n".join(txt)

        # ─────────────────────────────────────────────────────────────────────
        #  RELATÓRIO HTML (TEMA ESCURO)
        # ─────────────────────────────────────────────────────────────────────

        def badge(ok): return '<span class="badge-ok">✓ OK</span>' if ok else '<span class="badge-fail">✗ REPROVADO</span>'
        def cor_sigma(v): return "#4ade80" if v >= 0 else "#f87171"

        def render_estado_html(idx, res, det):
            face_c = face_comp(det['is_neg'])
            face_t = face_trac(det['is_neg'])
            M_abs  = det['M_abs_kNcm']
            x      = det['x']
            atd    = det['aco_tens_det']
            acd    = det['aco_comp_det']
            J      = det['J_total']

            # Tabela de fatias
            rows_fat = ""
            for i, fd in enumerate(det["fatias_det"], 1):
                rows_fat += (
                    f"<tr>"
                    f"<td>{i}</td><td>{fd['y1']:.3f}</td><td>{fd['y2']:.3f}</td>"
                    f"<td>{fd['b']:.2f}</td><td>{fd['hb']:.3f}</td>"
                    f"<td>{fd['area']:.3f}</td><td>{fd['cg']:.3f}</td>"
                    f"<td>{fd['braco']:.3f}</td>"
                    f"<td>{fd['Ip']:.2f}</td><td>{fd['St']:.2f}</td>"
                    f"<td><strong>{fd['J']:.2f}</strong></td>"
                    f"</tr>"
                )

            # Tabela de bissecção
            rows_bis = ""
            for it in det["hist_bis"]:
                ni, ai, bi, mi, fai, fmi = it
                cls = "style='color:#4ade80;'" if fai * fmi < 0 else ""
                rows_bis += (
                    f"<tr><td>{ni}</td><td>{ai:.4f}</td><td>{bi:.4f}</td>"
                    f"<td><strong>{mi:.4f}</strong></td>"
                    f"<td {cls}>{fai:.4f}</td><td {cls}>{fmi:.4f}</td></tr>"
                )

            aco_comp_html = ""
            if acd:
                aco_comp_html = f"""
                <p class="formula-eq">J<sub>aço_comp</sub> = n × A<sub>s,comp</sub> × (x − d<sub>comp</sub>)²
                    = {acd['n']:.4f} × {acd['As']:.4f} × ({x:.4f} − {acd['d']:.4f})²
                    = <strong>{det['J_aco_comp']:.4f} cm⁴</strong></p>"""

            sigma_tens_kN = m.n * M_abs * atd['braco'] / J
            sigma_comp_kN = 0.0
            sigma_comp_html = ""
            if acd:
                sigma_comp_kN = -m.n * M_abs * acd['braco'] / J
                sigma_comp_html = f"""
                <p class="formula-eq">σ<sub>comp</sub> = −n × M × (x − d<sub>comp</sub>) / J
                    = −{m.n:.4f} × {M_abs:.4f} × {acd['braco']:.4f} / {J:.4f}
                    = {sigma_comp_kN:.4f} kN/cm² = <strong>{sigma_comp_kN*10:.4f} MPa</strong></p>"""

            return f"""
        <div class="section">
            <div class="section-title">📊 SEÇÃO {idx+2} – ESTADO DE TENSÕES {idx}
            &nbsp;<span style="font-size:0.85em;font-weight:normal;">M<sub>sd,{idx}</sub> = {res.momento_sd:+.2f} kN.m</span></div>
            
            <div class="info-box">
                <p>Face comprimida (y = 0): <strong>{face_c}</strong> &nbsp;|&nbsp;
                   Face tracionada: <strong>{face_t}</strong></p>
                <p>A<sub>s,tens</sub> = {det['arms']['As_tens']:.2f} cm² (d<sub>tens</sub> = {det['arms']['d_tens']:.2f} cm)
                {'&nbsp;|&nbsp; A<sub>s,comp</sub> = ' + str(round(det["arms"]["As_comp"],2)) + ' cm² (d<sub>comp</sub> = ' + str(round(det["arms"]["d_comp"],2)) + ' cm)' if acd else ''}</p>
            </div>

            <p class="sub-title">► {idx+2}.1 Determinação da Linha Neutra – Bissecção</p>
            <p>Equilíbrio de momentos estáticos em relação à L.N. (S(x) = 0):</p>
            <p class="formula-eq">S(x) = Σ[b<sub>i</sub>·h<sub>i</sub>·(x−ȳ<sub>i</sub>)] + n·A<sub>s,comp</sub>·(x−d<sub>comp</sub>) − n·A<sub>s,tens</sub>·(d<sub>tens</sub>−x) = 0</p>
            <p>Intervalo inicial: a = 0,0001 cm &nbsp;|&nbsp; b = {det['arms']['d_tens']:.4f} cm</p>
            <table>
                <thead><tr>
                    <th>Iter</th><th>a [cm]</th><th>b [cm]</th><th>x_mid [cm]</th>
                    <th>S(a) [cm³]</th><th>S(x_mid) [cm³]</th>
                </tr></thead>
                <tbody>{rows_bis}</tbody>
            </table>
            <p style="font-style:italic;color:#94a3b8;">... convergência em {det['n_iter_total']} iterações (tol = 1×10⁻⁸ cm)</p>
            <p class="resultado-destaque">x = {x:.4f} cm</p>

            <p class="sub-title">► {idx+2}.2 Inércia Fissurada Homogenizada (J_fiss)</p>
            <p>Para cada fatia de concreto comprimida: J<sub>i</sub> = b<sub>i</sub>·h<sub>i</sub>³/12 + b<sub>i</sub>·h<sub>i</sub>·(x−ȳ<sub>i</sub>)²</p>
            <div style="overflow-x:auto;">
            <table>
                <thead><tr>
                    <th>#</th><th>y₁ [cm]</th><th>y₂ [cm]</th><th>b [cm]</th><th>h [cm]</th>
                    <th>Área [cm²]</th><th>ȳ [cm]</th><th>Braço [cm]</th>
                    <th>I_prop [cm⁴]</th><th>Steiner [cm⁴]</th><th>J_fat [cm⁴]</th>
                </tr></thead>
                <tbody>{rows_fat}</tbody>
            </table>
            </div>
            <p>Σ J<sub>concreto</sub> = <strong>{det['J_conc']:.4f} cm⁴</strong></p>
            {aco_comp_html}
            <p class="formula-eq">J<sub>aço_tens</sub> = n × A<sub>s,tens</sub> × (d<sub>tens</sub> − x)²
                = {atd['n']:.4f} × {atd['As']:.4f} × ({atd['d']:.4f} − {x:.4f})²
                = <strong>{det['J_aco_tens']:.4f} cm⁴</strong></p>
            <p class="formula-eq">J<sub>fiss</sub> = {det['J_conc']:.4f} + {det['J_aco_comp']:.4f} + {det['J_aco_tens']:.4f}
                = <strong>{det['J_total']:.4f} cm⁴ = {det['J_total']/1e8:.6f} m⁴</strong></p>
            <p class="resultado-destaque">J_fiss = {det['J_total']:.2f} cm⁴</p>

            <p class="sub-title">► {idx+2}.3 Tensões nas Armaduras</p>
            <p>Fórmula: σ<sub>s</sub> [MPa] = n × M<sub>abs</sub>[kN.cm] × y<sub>rel</sub> / J<sub>fiss</sub> × 10</p>
            <p class="formula-eq">σ<sub>tens</sub> = {m.n:.4f} × {M_abs:.4f} × {atd['braco']:.4f} / {J:.4f}
                = {sigma_tens_kN:.6f} kN/cm²
                = <strong>{sigma_tens_kN*10:.4f} MPa</strong> (tração)</p>
            {sigma_comp_html}
            <table style="margin-top:12px;">
                <tr>
                    <td>σ<sub>inf,{idx}</sub></td>
                    <td><strong style="color:{cor_sigma(res.sigma_inf_MPa)};font-size:1.1em;">{res.sigma_inf_MPa:+.4f} MPa</strong></td>
                    <td style="color:#94a3b8;">{'tração' if res.sigma_inf_MPa >= 0 else 'compressão'}</td>
                </tr>
                <tr>
                    <td>σ<sub>sup,{idx}</sub></td>
                    <td><strong style="color:{cor_sigma(res.sigma_sup_MPa)};font-size:1.1em;">{res.sigma_sup_MPa:+.4f} MPa</strong></td>
                    <td style="color:#94a3b8;">{'tração' if res.sigma_sup_MPa >= 0 else 'compressão'}</td>
                </tr>
            </table>
        </div>
"""

        html_estado1 = render_estado_html(1, r1, det1)
        html_estado2 = render_estado_html(2, r2, det2)

        # Bloco verificação armadura inferior
        bloco_inf_html = ""
        if m.As_inf > 0:
            corr_inf = (f"<p class='formula-eq'>A<sub>s,inf,corr</sub> = A<sub>s,inf</sub> × k / η "
                        f"= {m.As_inf:.4f} × {r.k_fad_inf:.6f} / {r.eta:.4f} = <strong>{r.as_inf_corrigida:.4f} cm²</strong></p>"
                        if not r.verifica_inf else
                        "<p>✓ Não há necessidade de correção da armadura inferior.</p>")
            bloco_inf_html = f"""
            <div style="background:#1a1a2e;padding:16px;border-radius:8px;margin-bottom:18px;">
                <p style="color:#60a5fa;font-weight:bold;font-size:1.05em;">Armadura Inferior (A<sub>s</sub>)</p>
                <p class="formula-eq">Δσ<sub>inf</sub> = |σ<sub>inf,1</sub> − σ<sub>inf,2</sub>|
                    = |({r1.sigma_inf_MPa:+.4f}) − ({r2.sigma_inf_MPa:+.4f})|
                    = <strong>{r.delta_sigma_inf_MPa:.4f} MPa</strong></p>
                <p class="formula-eq">k<sub>fad,inf</sub> = Δσ<sub>inf</sub> / Δf<sub>fad,sd,inf</sub>
                    = {r.delta_sigma_inf_MPa:.4f} / {r.delta_f_fad_sd_inf:.2f}
                    = <strong>{r.k_fad_inf:.6f}</strong></p>
                <p>Verificação: k<sub>fad,inf</sub> = {r.k_fad_inf:.4f} &nbsp; {badge(r.verifica_inf)}</p>
                {corr_inf}
                <p>A<sub>s,inf,corrigida</sub> = <strong>{r.as_inf_corrigida}</strong></p>
            </div>"""

        bloco_sup_html = ""
        if m.As_sup > 0:
            corr_sup = (f"<p class='formula-eq'>A<sub>s,sup,corr</sub> = A<sub>s,sup</sub> × k / η "
                        f"= {m.As_sup:.4f} × {r.k_fad_sup:.6f} / {r.eta:.4f} = <strong>{r.as_sup_corrigida:.4f} cm²</strong></p>"
                        if not r.verifica_sup else
                        "<p>✓ Não há necessidade de correção da armadura superior.</p>")
            bloco_sup_html = f"""
            <div style="background:#1a1a2e;padding:16px;border-radius:8px;margin-bottom:18px;">
                <p style="color:#60a5fa;font-weight:bold;font-size:1.05em;">Armadura Superior (A'<sub>s</sub>)</p>
                <p class="formula-eq">Δσ<sub>sup</sub> = |σ<sub>sup,1</sub> − σ<sub>sup,2</sub>|
                    = |({r1.sigma_sup_MPa:+.4f}) − ({r2.sigma_sup_MPa:+.4f})|
                    = <strong>{r.delta_sigma_sup_MPa:.4f} MPa</strong></p>
                <p class="formula-eq">k<sub>fad,sup</sub> = Δσ<sub>sup</sub> / Δf<sub>fad,sd,sup</sub>
                    = {r.delta_sigma_sup_MPa:.4f} / {r.delta_f_fad_sd_sup:.2f}
                    = <strong>{r.k_fad_sup:.6f}</strong></p>
                <p>Verificação: k<sub>fad,sup</sub> = {r.k_fad_sup:.4f} &nbsp; {badge(r.verifica_sup)}</p>
                {corr_sup}
                <p>A<sub>s,sup,corrigida</sub> = <strong>{r.as_sup_corrigida}</strong></p>
            </div>"""

        # Tabela síntese final
        rows_sint = ""
        if m.As_inf > 0:
            rows_sint += (
                f"<tr><td>Inferior (A<sub>s</sub>)</td>"
                f"<td style='color:{cor_sigma(r1.sigma_inf_MPa)}'>{r1.sigma_inf_MPa:+.4f}</td>"
                f"<td style='color:{cor_sigma(r2.sigma_inf_MPa)}'>{r2.sigma_inf_MPa:+.4f}</td>"
                f"<td>{r.delta_sigma_inf_MPa:.4f}</td>"
                f"<td>{r.delta_f_fad_sd_inf:.2f}</td>"
                f"<td><strong>{r.k_fad_inf:.4f}</strong></td>"
                f"<td>{badge(r.verifica_inf)}</td>"
                f"<td>{r.as_inf_corrigida if isinstance(r.as_inf_corrigida, str) else str(round(r.as_inf_corrigida,4))+' cm²'}</td>"
                f"</tr>"
            )
        if m.As_sup > 0:
            rows_sint += (
                f"<tr><td>Superior (A'<sub>s</sub>)</td>"
                f"<td style='color:{cor_sigma(r1.sigma_sup_MPa)}'>{r1.sigma_sup_MPa:+.4f}</td>"
                f"<td style='color:{cor_sigma(r2.sigma_sup_MPa)}'>{r2.sigma_sup_MPa:+.4f}</td>"
                f"<td>{r.delta_sigma_sup_MPa:.4f}</td>"
                f"<td>{r.delta_f_fad_sd_sup:.2f}</td>"
                f"<td><strong>{r.k_fad_sup:.4f}</strong></td>"
                f"<td>{badge(r.verifica_sup)}</td>"
                f"<td>{r.as_sup_corrigida if isinstance(r.as_sup_corrigida, str) else str(round(r.as_sup_corrigida,4))+' cm²'}</td>"
                f"</tr>"
            )

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #0f172a; color: #e2e8f0; padding: 20px; font-size: 14px; line-height: 1.6; }}
    .container {{ max-width: 1100px; margin: 0 auto; background: #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
    .header {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #1a237e 100%); padding: 28px; text-align: center; color: white; }}
    .header h1 {{ margin: 0 0 6px 0; font-size: 1.55em; letter-spacing: 0.5px; }}
    .header p  {{ margin: 0; opacity: 0.8; font-size: 0.92em; }}
    .content {{ padding: 28px; }}
    .section {{ margin-bottom: 28px; border-left: 4px solid #3b82f6; padding: 18px 18px 18px 20px; background: rgba(30,40,60,0.5); border-radius: 0 10px 10px 0; }}
    .section-title {{ font-size: 1.15em; font-weight: bold; color: #93c5fd; margin-bottom: 14px; border-bottom: 1px solid #334155; padding-bottom: 8px; }}
    .sub-title {{ color: #7dd3fc; font-weight: bold; margin: 18px 0 8px 0; font-size: 0.98em; }}
    .info-box {{ background: rgba(15,23,42,0.6); border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; border-left: 3px solid #6366f1; }}
    .formula-eq {{ background: #0f172a; border-left: 3px solid #f59e0b; padding: 10px 14px; font-family: 'Courier New', monospace; color: #fef3c7; font-size: 0.93em; margin: 8px 0; border-radius: 0 6px 6px 0; white-space: pre-wrap; }}
    .resultado-destaque {{ background: #1e3a5f; border: 1px solid #3b82f6; border-radius: 6px; padding: 8px 14px; font-size: 1.08em; font-weight: bold; color: #93c5fd; margin: 10px 0; display: inline-block; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 0.88em; }}
    th {{ background: #1e3a5f; color: #93c5fd; padding: 7px 10px; text-align: center; border-bottom: 2px solid #3b82f6; }}
    td {{ padding: 6px 10px; border-bottom: 1px solid #1e293b; text-align: center; }}
    tr:hover td {{ background: rgba(59,130,246,0.08); }}
    td:first-child {{ text-align: left; color: #94a3b8; }}
    .badge-ok   {{ background: #166534; color: #4ade80; padding: 2px 10px; border-radius: 12px; font-size: 0.85em; font-weight: bold; border: 1px solid #16a34a; }}
    .badge-fail {{ background: #7f1d1d; color: #f87171; padding: 2px 10px; border-radius: 12px; font-size: 0.85em; font-weight: bold; border: 1px solid #dc2626; }}
    .sintese-table th {{ font-size: 0.85em; }}
    .footer {{ background: #0f172a; padding: 14px; text-align: center; color: #475569; font-size: 0.82em; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>⚙️ Memorial de Cálculo – Fadiga na Flexão (Estádio II)</h1>
        <p>Verificação das tensões nas armaduras · NBR 6118:2014 · Motor Numérico por Fatias + Bissecção</p>
    </div>
    <div class="content">

        <!-- SEÇÃO 1 – DADOS DE ENTRADA -->
        <div class="section">
            <div class="section-title">📌 SEÇÃO 1 – DADOS DE ENTRADA</div>
            <div class="grid-2">
                <div>
                    <p class="sub-title">1.1 Geometria da Seção</p>
                    <table>
                        <tr><td>Tipo de Seção</td><td><strong>{m.dados.get('Tipo')}</strong></td></tr>
                        <tr><td>Altura Total (H)</td><td><strong>{m.H_total:.2f} cm</strong></td></tr>
                        {'<tr><td>Largura da alma (bw)</td><td><strong>' + str(m.dados.get("bw","–")) + ' cm</strong></td></tr>' if "bw" in m.dados else ''}
                        {'<tr><td>Largura da mesa (bf)</td><td><strong>' + str(m.dados.get("bf","–")) + ' cm</strong></td></tr>' if "bf" in m.dados else ''}
                        {'<tr><td>Esp. da mesa (hf)</td><td><strong>' + str(m.dados.get("hf","–")) + ' cm</strong></td></tr>' if "hf" in m.dados else ''}
                        {'<tr><td>Laje (h_L × b_L)</td><td><strong>' + f'{m.h_laje:.1f} × {m.b_laje:.1f} cm' + '</strong></td></tr>' if m.h_laje > 0 else ''}
                    </table>
                    <p class="sub-title">1.2 Relação Modular</p>
                    <table>
                        <tr><td>n = E<sub>s</sub>/E<sub>c</sub></td><td><strong>{m.n:.4f}</strong></td></tr>
                    </table>
                </div>
                <div>
                    <p class="sub-title">1.3 Armaduras</p>
                    <table>
                        <tr><td>A<sub>s,inf</sub> (inferior)</td><td><strong>{m.As_inf:.4f} cm²</strong></td></tr>
                        <tr><td>d<sub>inf</sub></td><td><strong>{m.d_inf:.2f} cm</strong></td></tr>
                        <tr><td>A<sub>s,sup</sub> (superior)</td><td><strong>{m.As_sup:.4f} cm²</strong></td></tr>
                        <tr><td>d<sub>sup</sub></td><td><strong>{m.d_sup:.2f} cm</strong></td></tr>
                    </table>
                    <p class="sub-title">1.4 Solicitações e Fadiga</p>
                    <table>
                        <tr><td>M<sub>sd,1</sub></td><td><strong>{r1.momento_sd:+.2f} kN.m</strong></td></tr>
                        <tr><td>M<sub>sd,2</sub></td><td><strong>{r2.momento_sd:+.2f} kN.m</strong></td></tr>
                        <tr><td>η (aproveitamento)</td><td><strong>{r.eta:.4f}</strong></td></tr>
                        <tr><td>Δf<sub>fad,sd,inf</sub></td><td><strong>{r.delta_f_fad_sd_inf:.2f} MPa</strong></td></tr>
                        <tr><td>Δf<sub>fad,sd,sup</sub></td><td><strong>{r.delta_f_fad_sd_sup:.2f} MPa</strong></td></tr>
                    </table>
                </div>
            </div>
        </div>

        <!-- SEÇÃO 2 – FATIAS -->
        <div class="section">
            <div class="section-title">🔲 SEÇÃO 2 – Discretização em Fatias (y = 0 na face comprimida)</div>
            <p>Para M<sub>sd,1</sub> = {r1.momento_sd:+.2f} kN.m → face comprimida: <strong>{face_comp(det1['is_neg'])}</strong></p>
            <table>
                <thead><tr><th>#</th><th>y_inic [cm]</th><th>y_fim [cm]</th><th>Largura [cm]</th></tr></thead>
                <tbody>
                    {''.join(f"<tr><td>{i}</td><td>{y1:.3f}</td><td>{y2:.3f}</td><td>{b:.2f}</td></tr>" for i,(y1,y2,b) in enumerate(det1['fatias_bruta'],1))}
                </tbody>
            </table>
            {'<p style="margin-top:12px;">Para M<sub>sd,2</sub> = ' + f'{r2.momento_sd:+.2f}' + ' kN.m → sinal invertido → seção rotacionada → face comprimida: <strong>' + face_comp(det2["is_neg"]) + '</strong></p><table><thead><tr><th>#</th><th>y_inic [cm]</th><th>y_fim [cm]</th><th>Largura [cm]</th></tr></thead><tbody>' + "".join(f"<tr><td>{i}</td><td>{y1:.3f}</td><td>{y2:.3f}</td><td>{b:.2f}</td></tr>" for i,(y1,y2,b) in enumerate(det2["fatias_bruta"],1)) + "</tbody></table>" if det1["is_neg"] != det2["is_neg"] else ""}
        </div>

        <!-- ESTADOS 1 e 2 -->
        {html_estado1}
        {html_estado2}

        <!-- VERIFICAÇÃO DE FADIGA -->
        <div class="section">
            <div class="section-title">✅ SEÇÃO 5 – Verificação à Fadiga (NBR 6118:2014, item 23.5.4)</div>
            <div class="info-box">
                <p>Condição: Δσ<sub>s,d</sub> ≤ Δf<sub>fad,s,d</sub> &nbsp;|&nbsp; k<sub>fad</sub> = Δσ<sub>s,d</sub> / Δf<sub>fad,s,d</sub> ≤ 1,0</p>
                <p>Correção (quando k &gt; 1): A<sub>s,corr</sub> = A<sub>s,orig</sub> × k / η</p>
            </div>
            {bloco_inf_html}
            {bloco_sup_html}

            <p class="sub-title">► SÍNTESE FINAL</p>
            <div style="overflow-x:auto;">
            <table class="sintese-table">
                <thead><tr>
                    <th>Armadura</th><th>σ₁ [MPa]</th><th>σ₂ [MPa]</th>
                    <th>Δσ [MPa]</th><th>Δf_fad [MPa]</th>
                    <th>k_fad</th><th>Status</th><th>As Corrigida</th>
                </tr></thead>
                <tbody>{rows_sint}</tbody>
            </table>
            </div>
        </div>

    </div>
    <div class="footer">
        Memorial de Cálculo gerado por Girder25 · Verificação à Fadiga (NBR 6118:2023) · Motor Numérico por Fatias + Bissecção
    </div>
</div>
</body>
</html>
"""
        return texto_plano, html


# ════════════════════════════════════════════════════════════════════════════════
# 4. BATERIA DE TESTES E VALIDAÇÃO ACADÊMICA
# ════════════════════════════════════════════════════════════════════════════════

def executar_testes():
    """
    Roda os 4 exemplos baseados nos slides do Prof. Rodrigo Pereira para validar 
    o motor numérico contra as respostas analíticas exatas.
    Demonstra também o uso dos novos parâmetros eta, delta_f_fad_sd_inf e delta_f_fad_sd_sup.
    """
    def _verificar(nome, calc_val, esp_val, tol):
        if abs(calc_val - esp_val) > tol:
            print(f"  [!] ALERTA em {nome}: Calculado={calc_val:.4f}, Esperado={esp_val:.4f}")
        else:
            print(f"  [✓] {nome} OK ({calc_val:.4f})")

    # ─── Instancia com limite padrão de 175 MPa ──────────────────────────────
    calc = CalculadoraFlexaoFadiga(delta_f_fad_sd=175.0)

    print("=" * 80)
    print("VALIDAÇÃO: CÁLCULO DE FADIGA (ESTÁDIO II) - EXEMPLOS ACADÊMICOS")
    print("=" * 80)

    # ─── EXEMPLO 1: Seção T, momentos M>0, só armadura inferior ────────────
    print("\nEXEMPLO 1 (Slides 60-66) – η=1.0, Δf_inf=175, Δf_sup=175 (padrão)")
    res_1 = calc.verificar_fadiga(
        dados_secao       = {"Tipo": "T", "bw": 40, "h": 190, "bf": 256, "hf": 25},
        M_1               = 2710.0, M_2=495.0,
        n_eq              = 10, As_inf=81.67, d_inf=180, As_sup=0.0,
        eta               = 1.0,
        delta_f_fad_sd_inf= 175.0,
        delta_f_fad_sd_sup= 175.0,
    )
    _verificar("LN (x)",      res_1.res_M1.x_cm,         31.34,  0.05)
    _verificar("Inércia (J)", res_1.res_M1.Jfiss_cm4/1e8, 0.2061, 0.005)
    _verificar("Tensão M1",   res_1.res_M1.sigma_inf_MPa, 195.5,  0.5)
    _verificar("Tensão M2",   res_1.res_M2.sigma_inf_MPa,  35.7,  0.5)
    _verificar("k_fad",       res_1.k_fad_inf,             0.913, 0.01)
    print(f"  As_inf_corrigida = {res_1.as_inf_corrigida}")
    print(f"  As_sup_corrigida = {res_1.as_sup_corrigida}")

    # ─── EXEMPLO 2: Seção T, M>0, armadura dupla ────────────────────────────
    print("\nEXEMPLO 2 (Slides 67-75) – η=0.9, Δf_inf=175, Δf_sup=150")
    res_2 = calc.verificar_fadiga(
        dados_secao       = {"Tipo": "T", "bw": 45, "h": 233, "bf": 381, "hf": 30},
        M_1               = 4498.0, M_2=1286.0,
        n_eq              = 6.77, As_inf=111.4, d_inf=223, As_sup=15.1, d_sup=10,
        eta               = 0.9,
        delta_f_fad_sd_inf= 175.0,
        delta_f_fad_sd_sup= 150.0,
    )
    _verificar("LN (x)",        res_2.res_M1.x_cm,          27.72, 0.05)
    _verificar("Tensão M1_inf", res_2.res_M1.sigma_inf_MPa, 188.7,  0.5)
    _verificar("Tensão M1_sup", res_2.res_M1.sigma_sup_MPa, -17.1,  0.5)
    print(f"  As_inf_corrigida = {res_2.as_inf_corrigida}")
    print(f"  As_sup_corrigida = {res_2.as_sup_corrigida}")

    # ─── EXEMPLO 3: Seção T, inversão de momentos (+ e -) ───────────────────
    print("\nEXEMPLO 3 (Slides 76-87) – INVERSÃO DE SINAIS – η=1.0, Δf_inf=160, Δf_sup=175")
    res_3 = calc.verificar_fadiga(
        dados_secao       = {"Tipo": "T", "bw": 40, "h": 190, "bf": 256, "hf": 25},
        M_1               = 1395.0, M_2=-595.0,
        n_eq              = 10, As_inf=48.5, d_inf=180, As_sup=32.99, d_sup=10,
        eta               = 1.0,
        delta_f_fad_sd_inf= 160.0,   # Δf diferente para armadura inferior
        delta_f_fad_sd_sup= 175.0,
    )
    _verificar("LN M1 (x)",     res_3.res_M1.x_cm,          23.64, 0.05)
    _verificar("Tensão M1_inf", res_3.res_M1.sigma_inf_MPa, 167.4,  0.5)
    _verificar("Tensão M2_inf", res_3.res_M2.sigma_inf_MPa, -22.9,  0.5)
    # Com Δf_inf=160, k_inf = |167.4−(−22.9)| / 160 = 190.3/160 = 1.189 → reprova
    print(f"  k_fad_inf        = {res_3.k_fad_inf:.4f}  (esperado ≈ 1.189 com Δf=160)")
    print(f"  Status Inf       = {'APROVADO' if res_3.verifica_inf else 'REPROVADO'}")
    print(f"  As_inf_corrigida = {res_3.as_inf_corrigida}")
    print(f"  As_sup_corrigida = {res_3.as_sup_corrigida}")

    # ─── EXEMPLO 4: Seção S15 (Projeto Real) ────────────────────────────────
    print("\nEXEMPLO 4 (Slides 88-95) – S15 – η=1.0, Δf_inf=175 (padrão)")
    res_4 = calc.verificar_fadiga(
        dados_secao       = {"Tipo": "T", "bw": 37.5, "h": 165, "bf": 251.5, "hf": 20},
        M_1               = 2377.9, M_2=918.0,
        n_eq              = 6.77, As_inf=78.15, d_inf=155, As_sup=0, d_sup=10,
        eta               = 1.0,
    )
    _verificar("LN (x)",      res_4.res_M1.x_cm,         23.75, 0.05)
    _verificar("Tensão M1",   res_4.res_M1.sigma_inf_MPa, 206.5,  0.5)
    _verificar("k_fad",       res_4.k_fad_inf,             0.724, 0.01)
    print(f"  As_inf_corrigida = {res_4.as_inf_corrigida}")

    print("\n" + "=" * 80)
    print("Demonstração do Memorial Completo (Exemplo 3 – com reprovação):")
    print("=" * 80)
    txt, html = calc.obter_relatorio_resumido()
    print(txt)

    # Opcional: salvar HTML para visualização
    with open("memorial_fadiga.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("\nArquivo 'memorial_fadiga.html' gerado com sucesso.")


if __name__ == "__main__":
    executar_testes()
