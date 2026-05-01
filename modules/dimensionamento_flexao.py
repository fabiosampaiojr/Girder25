"""
dimensionamento_flexao.py
=========================
Dimensionamento de seções de concreto armado à FLEXÃO SIMPLES
conforme NBR 6118:2014 — método do bloco retangular de tensões.

A seção transversal é descrita como uma composição de retângulos, o que
permite tratar de forma UNIFICADA:

    ┌─────────────┐   Tipo de seção         Factory function
    │ Retangular  │ → criar_secao_retangular()
    │ Viga T      │ → criar_secao_T()
    │ Viga I      │ → criar_secao_I()
    │ T + Laje    │ → criar_secao_T_com_laje()
    │ I + Laje    │ → criar_secao_I_com_laje()
    │ Ret + Laje  │ → criar_secao_retangular_com_laje()
    └─────────────┘

Convenções de unidades:
    • Comprimentos  : centímetros  [cm]
    • Forças        : quilonewtons [kN]
    • Momentos      : kN·m
    • Tensões       : megapascal  [MPa]

Convenções de sinal:
    • Momento POSITIVO → sagging  (compressão no TOPO,  tração na base)
    • Momento NEGATIVO → hogging  (compressão na BASE,  tração no topo)

Referências:
    • NBR 6118:2014 itens 14.6.4, 17.2.2, 17.3.5
    • Pinheiro, Libânio M. — Fundamentos de Concreto Armado, Cap. 7
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


# ══════════════════════════════════════════════════════════════════════════════
# 1.  ENUMERAÇÕES
# ══════════════════════════════════════════════════════════════════════════════

class ClasseDuctilidade(Enum):
    """
    Classe de ductilidade conforme NBR 6118:2014, Tabela 7.1.

    NORMAL   → kx_lim = 0,45  (fck ≤ 50 MPa)
    ESPECIAL → kx_lim = 0,35  (fck ≤ 50 MPa)  — recomendado para pontes
    """
    NORMAL   = "normal"
    ESPECIAL = "especial"


# ══════════════════════════════════════════════════════════════════════════════
# 2.  CLASSES DE DADOS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Retangulo:
    """
    Retângulo primitivo que compõe a seção transversal.

    Atributos:
        b      : largura [cm]
        h      : altura  [cm]
        y_base : ordenada da face inferior do retângulo, medida desde a
                 fibra mais baixa de toda a seção [cm]
                 Convenção global: y = 0 na base da seção.
        nome   : rótulo descritivo (ex.: "alma", "mesa_sup", "laje") — apenas
                 para legibilidade dos relatórios; não afeta o cálculo.

    Propriedades calculadas:
        y_topo : face superior do retângulo  [cm]
        area   : área do retângulo           [cm²]
        y_cg   : centroide do retângulo      [cm] medido da base
    """
    b: float
    h: float
    y_base: float = 0.0
    nome: str = ""

    @property
    def y_topo(self) -> float:
        return self.y_base + self.h

    @property
    def area(self) -> float:
        return self.b * self.h

    @property
    def y_cg(self) -> float:
        return self.y_base + self.h / 2.0

    def __repr__(self) -> str:
        tag = f" [{self.nome}]" if self.nome else ""
        return (
            f"Retangulo{tag}: b={self.b:.1f} cm, h={self.h:.1f} cm, "
            f"y∈[{self.y_base:.1f}, {self.y_topo:.1f}] cm"
        )


@dataclass
class ParametrosGeometricos:
    """
    Geometria e propriedades de material de uma seção transversal genérica.

    A seção é descrita pela lista `retangulos`; qualquer composição de
    retângulos é aceita, inclusive seções com vazios (não suportado nesta
    versão — seções maciças apenas).

    Atributos obrigatórios:
        retangulos  : componentes retangulares, em qualquer ordem.
        d_pos       : altura útil para momento POSITIVO [cm]
                      (do topo à armadura de tração inferior)
        d_neg       : altura útil para momento NEGATIVO [cm]
                      (da base à armadura de tração superior)

    Atributos opcionais:
        fck         : resistência característica do concreto [MPa]  (padrão 30)
        fyk         : resistência característica do aço       [MPa]  (padrão 500)
        gamma_c     : coeficiente de ponderação do concreto          (padrão 1,4)
        gamma_s     : coeficiente de ponderação do aço               (padrão 1,15)
        ductilidade : ClasseDuctilidade — ver enum                   (padrão NORMAL)
    """
    retangulos  : List[Retangulo]
    d_pos       : float
    d_neg       : float
    fck         : float = 30.0
    fyk         : float = 500.0
    gamma_c     : float = 1.4
    gamma_s     : float = 1.15
    ductilidade : ClasseDuctilidade = ClasseDuctilidade.NORMAL

    def __post_init__(self) -> None:
        # Ordena os retângulos de baixo para cima (facilita depuração)
        self.retangulos = sorted(self.retangulos, key=lambda r: r.y_base)
        # Validações básicas
        if not self.retangulos:
            raise ValueError("A seção deve ter pelo menos um retângulo.")
        if self.d_pos <= 0 or self.d_neg <= 0:
            raise ValueError("d_pos e d_neg devem ser positivos.")

    # ── propriedades derivadas ──────────────────────────────────────────────

    @property
    def h_total(self) -> float:
        """Altura total da seção (do topo ao mais alto retângulo) [cm]."""
        return max(r.y_topo for r in self.retangulos)

    @property
    def area_bruta(self) -> float:
        """Área bruta de concreto [cm²]."""
        return sum(r.area for r in self.retangulos)

    @property
    def y_cg_bruto(self) -> float:
        """Centroide da seção bruta medido da base [cm]."""
        return (
            sum(r.area * r.y_cg for r in self.retangulos) / self.area_bruta
        )

    @property
    def bw(self) -> float:
        """
        Menor largura da seção (≈ largura da alma).
        Usada no cálculo da armadura mínima (NBR 6118 item 17.3.5.2).
        """
        return min(r.b for r in self.retangulos)


@dataclass
class ResultadoDimensionamento:
    """
    Resultado completo do dimensionamento à flexão simples.

    Todos os campos são preenchidos pela função `dimensionar_flexao_simples`.
    """
    # ── entradas resumidas ──────────────────────────────────────────────────
    Msd           : float  # momento de cálculo [kN·m]
    sinal_momento : str    # "positivo" ou "negativo"

    # ── parâmetros de cálculo ───────────────────────────────────────────────
    d      : float  # altura útil utilizada [cm]
    fcd    : float  # resistência de cálculo do concreto [MPa]
    fyd    : float  # resistência de cálculo do aço [MPa]
    kx_lim : float  # limite de kx para flexão simples

    # ── resultados do bloco de compressão ──────────────────────────────────
    a   : float   # profundidade do bloco de compressão (a = λ·x)  [cm]
    x   : float   # posição da linha neutra                         [cm]
    kx  : float   # posição relativa da linha neutra (x/d)          [−]
    z   : float   # braço de alavanca interno                       [cm]
    Fcc : float   # resultante de compressão no concreto            [kN]

    # ── armadura de tração ─────────────────────────────────────────────────
    As_calc   : float  # área calculada                [cm²]
    As_min    : float  # área mínima (NBR 6118)        [cm²]
    As_adotar : float  # max(As_calc, As_min)          [cm²]

    # ── flags de status ─────────────────────────────────────────────────────
    armadura_dupla_necessaria : bool = False
    secao_insuficiente        : bool = False

    # ── dados de armadura dupla (preenchidos apenas quando necessário) ──────
    Mrd_lim      : Optional[float] = None  # momento resistido no limite [kN·m]
    delta_M      : Optional[float] = None  # momento excedente           [kN·m]
    As_linha     : Optional[float] = None  # armadura de compressão A's  [cm²]
    As_adicional : Optional[float] = None  # adicional na tração         [cm²]
    d_linha      : Optional[float] = None  # cobrimento da A's           [cm]

    # ── alertas e avisos ────────────────────────────────────────────────────
    alertas : List[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# 3.  FACTORY FUNCTIONS  (construtores de seção)
# ══════════════════════════════════════════════════════════════════════════════

def criar_secao_retangular(
    bw: float,
    h: float,
    d_pos: float,
    d_neg: float,
    fck: float = 30.0,
    fyk: float = 500.0,
    gamma_c: float = 1.4,
    gamma_s: float = 1.15,
    ductilidade: ClasseDuctilidade = ClasseDuctilidade.NORMAL,
) -> ParametrosGeometricos:
    """
    Seção retangular simples.

    Args:
        bw    : largura da seção [cm]
        h     : altura total     [cm]
    """
    rects = [Retangulo(b=bw, h=h, y_base=0.0, nome="alma")]
    return ParametrosGeometricos(
        rects, d_pos, d_neg, fck, fyk, gamma_c, gamma_s, ductilidade
    )


def criar_secao_T(
    bw: float,
    h_alma: float,
    bf: float,
    hf: float,
    d_pos: float,
    d_neg: float,
    fck: float = 30.0,
    fyk: float = 500.0,
    gamma_c: float = 1.4,
    gamma_s: float = 1.15,
    ductilidade: ClasseDuctilidade = ClasseDuctilidade.NORMAL,
) -> ParametrosGeometricos:
    """
    Seção T com mesa no topo (moldada monoliticamente).

    Args:
        bw     : largura da alma           [cm]
        h_alma : altura da alma (sem mesa) [cm]
        bf     : largura total da mesa     [cm]
        hf     : espessura da mesa         [cm]

    Geometria resultante (y medido da base):
        y ∈ [0,      h_alma]        → alma  (largura bw)
        y ∈ [h_alma, h_alma+hf]     → mesa  (largura bf)
    """
    rects = [
        Retangulo(b=bw, h=h_alma, y_base=0.0,    nome="alma"),
        Retangulo(b=bf, h=hf,     y_base=h_alma, nome="mesa_sup"),
    ]
    return ParametrosGeometricos(
        rects, d_pos, d_neg, fck, fyk, gamma_c, gamma_s, ductilidade
    )


def criar_secao_I(
    bw: float,
    h_alma: float,
    bf_sup: float,
    hf_sup: float,
    bf_inf: float,
    hf_inf: float,
    d_pos: float,
    d_neg: float,
    fck: float = 30.0,
    fyk: float = 500.0,
    gamma_c: float = 1.4,
    gamma_s: float = 1.15,
    ductilidade: ClasseDuctilidade = ClasseDuctilidade.NORMAL,
) -> ParametrosGeometricos:
    """
    Seção I com mesas na base e no topo.

    Args:
        bw      : largura da alma            [cm]
        h_alma  : altura da alma (sem mesas) [cm]
        bf_sup  : largura da mesa superior   [cm]
        hf_sup  : espessura da mesa superior [cm]
        bf_inf  : largura da mesa inferior   [cm]
        hf_inf  : espessura da mesa inferior [cm]

    Geometria resultante (y medido da base):
        y ∈ [0,             hf_inf]              → mesa inferior (bf_inf)
        y ∈ [hf_inf,        hf_inf+h_alma]       → alma          (bw)
        y ∈ [hf_inf+h_alma, hf_inf+h_alma+hf_sup]→ mesa superior (bf_sup)
    """
    rects = [
        Retangulo(b=bf_inf, h=hf_inf,  y_base=0.0,              nome="mesa_inf"),
        Retangulo(b=bw,     h=h_alma,  y_base=hf_inf,           nome="alma"),
        Retangulo(b=bf_sup, h=hf_sup,  y_base=hf_inf + h_alma,  nome="mesa_sup"),
    ]
    return ParametrosGeometricos(
        rects, d_pos, d_neg, fck, fyk, gamma_c, gamma_s, ductilidade
    )


def criar_secao_T_com_laje(
    bw: float,
    h_viga: float,
    b_laje: float,
    h_laje: float,
    d_pos: float,
    d_neg: float,
    fck: float = 30.0,
    fyk: float = 500.0,
    gamma_c: float = 1.4,
    gamma_s: float = 1.15,
    ductilidade: ClasseDuctilidade = ClasseDuctilidade.NORMAL,
) -> ParametrosGeometricos:
    """
    Seção T formada por viga retangular + laje colaborante no topo.

    A largura efetiva b_laje deve ser pré-calculada conforme
    NBR 6118:2014 item 15.3.3 (regras da mesa colaborante).

    Args:
        bw     : largura da viga             [cm]
        h_viga : altura total da viga        [cm]  (sem a laje)
        b_laje : largura efetiva da laje     [cm]
        h_laje : espessura da laje           [cm]

    Geometria resultante (y medido da base):
        y ∈ [0,      h_viga]         → viga (bw)
        y ∈ [h_viga, h_viga+h_laje]  → laje colaborante (b_laje)
    """
    rects = [
        Retangulo(b=bw,     h=h_viga,  y_base=0.0,     nome="viga"),
        Retangulo(b=b_laje, h=h_laje,  y_base=h_viga,  nome="laje_colaborante"),
    ]
    return ParametrosGeometricos(
        rects, d_pos, d_neg, fck, fyk, gamma_c, gamma_s, ductilidade
    )


def criar_secao_I_com_laje(
    bw: float,
    h_alma: float,
    bf_inf: float,
    hf_inf: float,
    b_laje: float,
    h_laje: float,
    d_pos: float,
    d_neg: float,
    fck: float = 30.0,
    fyk: float = 500.0,
    gamma_c: float = 1.4,
    gamma_s: float = 1.15,
    ductilidade: ClasseDuctilidade = ClasseDuctilidade.NORMAL,
) -> ParametrosGeometricos:
    """
    Seção I pré-moldada + laje moldada in loco — configuração típica de pontes.

    A mesa superior da viga I é substituída (ou complementada) pela laje
    colaborante, que constitui a largura efetiva do tabuleiro.

    Args:
        bw      : largura da alma             [cm]
        h_alma  : altura da alma (sem mesas)  [cm]
        bf_inf  : largura da mesa inferior    [cm]
        hf_inf  : espessura da mesa inferior  [cm]
        b_laje  : largura efetiva da laje     [cm]
        h_laje  : espessura da laje           [cm]

    Geometria resultante (y medido da base):
        y ∈ [0,                  hf_inf]              → mesa inferior (bf_inf)
        y ∈ [hf_inf,             hf_inf+h_alma]       → alma          (bw)
        y ∈ [hf_inf+h_alma,      hf_inf+h_alma+h_laje]→ laje          (b_laje)
    """
    rects = [
        Retangulo(b=bf_inf, h=hf_inf,  y_base=0.0,              nome="mesa_inf"),
        Retangulo(b=bw,     h=h_alma,  y_base=hf_inf,           nome="alma"),
        Retangulo(b=b_laje, h=h_laje,  y_base=hf_inf + h_alma,  nome="laje_colaborante"),
    ]
    return ParametrosGeometricos(
        rects, d_pos, d_neg, fck, fyk, gamma_c, gamma_s, ductilidade
    )


def criar_secao_retangular_com_laje(
    bw: float,
    h_viga: float,
    b_laje: float,
    h_laje: float,
    d_pos: float,
    d_neg: float,
    fck: float = 30.0,
    fyk: float = 500.0,
    gamma_c: float = 1.4,
    gamma_s: float = 1.15,
    ductilidade: ClasseDuctilidade = ClasseDuctilidade.NORMAL,
) -> ParametrosGeometricos:
    """
    Seção retangular + laje colaborante no topo.

    Geometricamente idêntica a criar_secao_T_com_laje, mas distinguida
    semanticamente: a alma tem seção constante (sem mesa pré-moldada).
    """
    return criar_secao_T_com_laje(
        bw, h_viga, b_laje, h_laje,
        d_pos, d_neg, fck, fyk, gamma_c, gamma_s, ductilidade,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 4.  FUNÇÕES AUXILIARES — propriedades de material e normativas
# ══════════════════════════════════════════════════════════════════════════════

def _fcd(fck: float, gamma_c: float) -> float:
    """Resistência de cálculo do concreto [MPa] — NBR 6118 item 12.3.3."""
    return fck / gamma_c


def _fyd(fyk: float, gamma_s: float) -> float:
    """
    Resistência de cálculo do aço [MPa] — NBR 6118 item 8.2.5.
    Limitado a fyk/γs; para CA-50 típico → 435 MPa.
    """
    return fyk / gamma_s


def _kx_lim(fck: float, ductilidade: ClasseDuctilidade) -> float:
    """
    Limite superior de kx = x/d para garantir ductilidade mínima.
    NBR 6118:2014, item 14.6.4.3 e Tabela 7.1.

        fck ≤ 50 MPa:
            Classe Normal   → kx_lim = 0,45
            Classe Especial → kx_lim = 0,35

        fck > 50 MPa (C55–C90): valores mais restritivos (simplificados).
    """
    if fck <= 50.0:
        return 0.45 if ductilidade == ClasseDuctilidade.NORMAL else 0.35
    # Concretos de alta resistência: interpolação linear simplificada
    return 0.35 if ductilidade == ClasseDuctilidade.NORMAL else 0.25


def _lambda_bloco(fck: float) -> float:
    """
    Coeficiente λ de altura do bloco retangular de tensões.
    NBR 6118:2014, item 17.2.2.
        fck ≤ 50 MPa  → λ = 0,80
        fck > 50 MPa  → λ = 0,80 − (fck − 50) / 400
    """
    if fck <= 50.0:
        return 0.80
    return 0.80 - (fck - 50.0) / 400.0


def _alpha_c(fck: float) -> float:
    """
    Fator αc de redução da resistência do concreto comprimido.
    NBR 6118:2014, item 17.2.2.
        fck ≤ 50 MPa  → αc = 0,85
        fck > 50 MPa  → αc = 0,85 · [1 − (fck − 50) / 200]
    """
    if fck <= 50.0:
        return 0.85
    return 0.85 * (1.0 - (fck - 50.0) / 200.0)


def _as_minima(fck: float, fyk: float, bw: float, d: float) -> float:
    """
    Área de armadura mínima de tração [cm²].
    NBR 6118:2014, item 17.3.5.2:
        ρ_mín = max(0,26 · fctm / fyk, 0,0013)
        fctm  = 0,3 · fck^(2/3)  para fck ≤ 50 MPa
        fctm  = 2,12 · ln(1 + fck/10) para fck > 50 MPa (simplificado)
    """
    if fck <= 50.0:
        fctm = 0.3 * (fck ** (2.0 / 3.0))
    else:
        fctm = 2.12 * math.log(1.0 + fck / 10.0)
    rho_min = max(0.26 * fctm / fyk, 0.0013)
    return rho_min * bw * d


# ══════════════════════════════════════════════════════════════════════════════
# 5.  NÚCLEO DO CÁLCULO — bloco de compressão genérico
# ══════════════════════════════════════════════════════════════════════════════

def _bloco_compressao(
    retangulos: List[Retangulo],
    a: float,
    h_total: float,
    compressao_no_topo: bool,
    fcd: float,
    fck: float,
) -> Tuple[float, float]:
    """
    Calcula a resultante de compressão Fcc e a posição do seu centroide,
    dado um bloco retangular de compressão de profundidade `a`.

    Sistema de coordenadas interno ξ:
        ξ = 0  →  face comprimida
        ξ = a  →  limite do bloco (ξ = λ·x)

    Conversão para o sistema global y (da base para cima):
        se compressao_no_topo:  ξ = h_total − y
        se compressao_na_base:  ξ = y

    Args:
        retangulos         : lista de retângulos da seção
        a                  : profundidade do bloco de compressão [cm]
        h_total            : altura total da seção               [cm]
        compressao_no_topo : True → momento positivo
        fcd                : resistência de cálculo do concreto [MPa]
        fck                : necessário para αc e λ

    Returns:
        Fcc   : força de compressão resultante [kN]
        xi_cg : centroide do bloco medido da face comprimida [cm]
    """
    ac = _alpha_c(fck)
    Fcc   = 0.0
    soma_xi = 0.0  # Σ(dF · ξ_centroide) — para cálculo do centroide ponderado

    for rect in retangulos:
        # ── limites do retângulo no sistema ξ ─────────────────────────────
        if compressao_no_topo:
            xi_rect_ini = h_total - rect.y_topo   # ξ do topo do retângulo
            xi_rect_fim = h_total - rect.y_base   # ξ da base do retângulo
        else:
            xi_rect_ini = rect.y_base
            xi_rect_fim = rect.y_topo

        # ── interseção com o bloco [0, a] ──────────────────────────────────
        xi1 = max(0.0, xi_rect_ini)
        xi2 = min(a,   xi_rect_fim)

        if xi2 <= xi1:
            continue  # sem interseção: retângulo fora do bloco

        # ── contribuição desta fatia ────────────────────────────────────────
        h_fatia = xi2 - xi1
        # Conversão de unidades: fcd [MPa] = fcd [kN/cm²] × 10
        # → F [kN] = αc × fcd [MPa] × b [cm] × h [cm] × 0,1
        dF = ac * fcd * rect.b * h_fatia * 0.1
        Fcc     += dF
        soma_xi += dF * (xi1 + xi2) / 2.0  # centroide da fatia em ξ

    xi_cg = soma_xi / Fcc if Fcc > 1.0e-9 else 0.0
    return Fcc, xi_cg


def _momento_bloco(
    retangulos: List[Retangulo],
    a: float,
    h_total: float,
    compressao_no_topo: bool,
    d: float,
    fcd: float,
    fck: float,
) -> float:
    """
    Momento resistente do concreto em relação à armadura de tração [kN·m].

    M = Fcc · z / 100   onde   z = d − ξ_cg   [cm → m: ÷100]
    """
    Fcc, xi_cg = _bloco_compressao(
        retangulos, a, h_total, compressao_no_topo, fcd, fck
    )
    z = d - xi_cg                 # braço de alavanca [cm]
    return Fcc * z / 100.0        # [kN·m]


def _bissetar_profundidade_bloco(
    retangulos: List[Retangulo],
    Msd: float,
    h_total: float,
    compressao_no_topo: bool,
    d: float,
    fcd: float,
    fck: float,
    tolerancia: float = 1.0e-6,
    max_iter: int = 120,
) -> float:
    """
    Determina a profundidade do bloco de compressão `a` tal que:

        Mcc(a) = Msd

    pelo método da bisseção (robusto e independente de derivadas).

    Returns:
        a    : profundidade do bloco [cm]
        nan  : se a seção for insuficiente (Mcc(a_max) < Msd)
    """
    a_min = 0.0
    a_max = d   # fisicamente, a ≤ d (braço nulo seria a = d)

    Mcc_max = _momento_bloco(
        retangulos, a_max, h_total, compressao_no_topo, d, fcd, fck
    )
    if Mcc_max < Msd:
        return float("nan")  # seção incapaz de resistir ao momento

    for _ in range(max_iter):
        a_mid = (a_min + a_max) / 2.0
        Mcc_mid = _momento_bloco(
            retangulos, a_mid, h_total, compressao_no_topo, d, fcd, fck
        )
        if abs(Mcc_mid - Msd) < tolerancia:
            return a_mid
        if Mcc_mid < Msd:
            a_min = a_mid
        else:
            a_max = a_mid

    return (a_min + a_max) / 2.0  # convergência por exaustão


# ══════════════════════════════════════════════════════════════════════════════
# 6.  FUNÇÃO PRINCIPAL DE DIMENSIONAMENTO
# ══════════════════════════════════════════════════════════════════════════════

def dimensionar_flexao_simples(
    geo: ParametrosGeometricos,
    Msd: float,
    d_linha_armadura: float = 5.0,
    calcular_armadura_dupla: bool = False,
) -> ResultadoDimensionamento:
    """
    Dimensiona a armadura longitudinal de tração à flexão simples,
    conforme NBR 6118:2014 — método do bloco retangular de tensões.

    ─── Fluxo do algoritmo ────────────────────────────────────────────────
    1. Identifica a face comprimida (sinal do momento).
    2. Calcula fcd, fyd, kx_lim, λ.
    3. Encontra a profundidade do bloco `a` por bisseção:
           Mcc(a) = Msd_abs
    4. Calcula kx = x/d.  Verifica se kx ≤ kx_lim.
    5a. kx ≤ kx_lim (flexão simples):
           As = Fcc / fyd
    5b. kx > kx_lim (armadura dupla necessária):
           - Fixa kx = kx_lim → calcula Mrd,lim.
           - ΔM = Msd − Mrd,lim.
           - A's = ΔM / (fyd · z') — armadura de compressão.
           - As  += A's adicional na tração.
    6. Verifica As_mínima.
    ─────────────────────────────────────────────────────────────────────

    Args:
        geo                    : geometria e materiais da seção
        Msd                    : momento de cálculo [kN·m]
                                 ≥ 0 → sagging (compressão no topo)
                                 < 0 → hogging (compressão na base)
        d_linha_armadura       : distância da face comprimida ao centroide
                                 da armadura de compressão A's, usado apenas
                                 no cálculo de armadura dupla [cm]. Padrão: 5 cm.
        calcular_armadura_dupla: se True, calcula A's quando kx > kx_lim;
                                 se False, apenas emite alerta.

    Returns:
        ResultadoDimensionamento com todos os campos preenchidos.
    """

    # ── preparação ─────────────────────────────────────────────────────────
    Msd_abs            = abs(Msd)
    compressao_no_topo = (Msd >= 0.0)
    sinal              = "positivo" if compressao_no_topo else "negativo"
    d                  = geo.d_pos if compressao_no_topo else geo.d_neg
    alertas: List[str] = []

    fcd_val  = _fcd(geo.fck,  geo.gamma_c)
    fyd_val  = _fyd(geo.fyk,  geo.gamma_s)
    kx_lim_v = _kx_lim(geo.fck, geo.ductilidade)
    lam      = _lambda_bloco(geo.fck)

    # ── passo 1: encontrar profundidade do bloco de compressão ────────────
    a_calc = _bissetar_profundidade_bloco(
        geo.retangulos, Msd_abs,
        geo.h_total, compressao_no_topo,
        d, fcd_val, geo.fck,
    )

    # ── tratamento: seção completamente insuficiente ──────────────────────
    if math.isnan(a_calc):
        alertas.append(
            "ERRO CRÍTICO: mesmo com todo o concreto trabalhando no limite, "
            "a seção não resiste ao momento solicitante. Aumente a altura ou "
            "a largura da seção."
        )
        a_calc = d  # usa o limite como referência para o relatório
        Fcc_val, xi_cg = _bloco_compressao(
            geo.retangulos, a_calc, geo.h_total,
            compressao_no_topo, fcd_val, geo.fck,
        )
        z_calc  = max(d - xi_cg, 1.0)
        x_calc  = a_calc / lam
        kx_calc = x_calc / d
        As_calc_val = Msd_abs * 100.0 / (fyd_val * 0.1 * z_calc)
        As_min_val  = _as_minima(geo.fck, geo.fyk, geo.bw, d)
        return ResultadoDimensionamento(
            Msd=Msd, sinal_momento=sinal,
            d=d, fcd=fcd_val, fyd=fyd_val, kx_lim=kx_lim_v,
            a=a_calc, x=x_calc, kx=kx_calc, z=z_calc, Fcc=Fcc_val,
            As_calc=As_calc_val, As_min=As_min_val, As_adotar=As_calc_val,
            secao_insuficiente=True, alertas=alertas,
        )

    # ── passo 2: linha neutra e verificação de ductilidade ────────────────
    x_calc  = a_calc / lam
    kx_calc = x_calc / d

    Fcc_val, xi_cg = _bloco_compressao(
        geo.retangulos, a_calc, geo.h_total,
        compressao_no_topo, fcd_val, geo.fck,
    )
    z_calc = d - xi_cg   # braço de alavanca [cm]

    # variáveis para armadura dupla (preenchidas abaixo se necessário)
    armadura_dupla = False
    Mrd_lim = delta_M = As_linha = As_adic = None

    # ── passo 3: verificar kx_lim ─────────────────────────────────────────
    if kx_calc > kx_lim_v:
        armadura_dupla = True
        alertas.append(
            f"kx calculado ({kx_calc:.4f}) > kx_lim ({kx_lim_v:.2f}): "
            "seção requer armadura dupla ou deve ser redimensionada."
        )
        alertas.append(
            "RECOMENDAÇÃO (pontes): prefira aumentar a altura ou o fck. "
            "Armadura dupla é recurso de última instância em longarinas."
        )

        # Fixa a linha neutra no limite
        x_lim  = kx_lim_v * d
        a_lim  = lam * x_lim
        Fcc_lim, xi_cg_lim = _bloco_compressao(
            geo.retangulos, a_lim, geo.h_total,
            compressao_no_topo, fcd_val, geo.fck,
        )
        z_lim   = d - xi_cg_lim
        Mrd_lim = Fcc_lim * z_lim / 100.0  # [kN·m]
        delta_M = Msd_abs - Mrd_lim

        # Atualiza os valores de referência para o cálculo de As de tração
        a_calc  = a_lim
        x_calc  = x_lim
        kx_calc = kx_lim_v
        Fcc_val = Fcc_lim
        z_calc  = z_lim

        if calcular_armadura_dupla:
            # ── braço de alavanca da armadura dupla ────────────────────────
            # z' = d − d'  (d' = distância da face comprimida ao centroide de A's)
            brac_dupla = d - d_linha_armadura

            if brac_dupla <= 0:
                alertas.append(
                    "ERRO: d' ≥ d — cobrimento da armadura de compressão inválido."
                )
                brac_dupla = max(brac_dupla, 0.1)

            # A's [cm²] = ΔM [kN·m] × 100 / (fyd [MPa] × 0,1 × z' [cm])
            #           = ΔM × 1000 / (fyd × z')
            As_linha = delta_M * 1000.0 / (fyd_val * brac_dupla)

            # O par de armadura dupla precisa de um adicional igual em tração
            As_adic = As_linha

            alertas.append(
                f"Armadura dupla calculada: "
                f"A's = {As_linha:.2f} cm²  (compressão, d'={d_linha_armadura} cm), "
                f"As_adicional = {As_adic:.2f} cm²  (tração)."
            )

    # ── passo 4: armadura de tração total ─────────────────────────────────
    # Equilíbrio de forças: Fcc = fyd × As_tração
    # As_base = Fcc / fyd [kN/cm²] = Fcc / (fyd [MPa] × 0,1)
    As_base = Fcc_val / (fyd_val * 0.1)

    # Adiciona a parcela de armadura dupla (se calculada)
    As_calc_val = As_base + (As_adic if As_adic is not None else 0.0)

    # ── passo 5: armadura mínima ──────────────────────────────────────────
    As_min_val = _as_minima(geo.fck, geo.fyk, geo.bw, d)
    As_adotar  = max(As_calc_val, As_min_val)

    if As_calc_val < As_min_val:
        alertas.append(
            f"As calculada ({As_calc_val:.2f} cm²) < As mínima ({As_min_val:.2f} cm²). "
            "Adotar a área mínima."
        )

    return ResultadoDimensionamento(
        Msd=Msd, sinal_momento=sinal,
        d=d, fcd=fcd_val, fyd=fyd_val, kx_lim=kx_lim_v,
        a=a_calc, x=x_calc, kx=kx_calc, z=z_calc, Fcc=Fcc_val,
        As_calc=As_calc_val, As_min=As_min_val, As_adotar=As_adotar,
        armadura_dupla_necessaria=armadura_dupla,
        Mrd_lim=Mrd_lim, delta_M=delta_M,
        As_linha=As_linha, As_adicional=As_adic,
        d_linha=d_linha_armadura if armadura_dupla else None,
        alertas=alertas,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7.  FORMATAÇÃO DO RESULTADO
# ══════════════════════════════════════════════════════════════════════════════

def imprimir_resultado(res: ResultadoDimensionamento, titulo: str = "") -> None:
    """Exibe o resultado de dimensionamento de forma legível no console."""
    SEP = "─" * 62
    TIT = "═" * 62

    print(f"\n{TIT}")
    if titulo:
        print(f"  {titulo}")
    print(f"  DIMENSIONAMENTO À FLEXÃO SIMPLES — NBR 6118:2014")
    print(TIT)
    print(f"  Msd              : {res.Msd:+10.2f} kN·m  ({res.sinal_momento})")
    print(f"  Altura útil  d   : {res.d:10.2f} cm")
    print(f"  fcd              : {res.fcd:10.2f} MPa")
    print(f"  fyd              : {res.fyd:10.2f} MPa")
    print(SEP)
    print(f"  Bloco  a = λ·x   : {res.a:10.3f} cm")
    print(f"  Linha neutra  x  : {res.x:10.3f} cm")
    print(f"  kx = x/d         : {res.kx:10.4f}   (kx_lim = {res.kx_lim:.2f})", end="")
    print("  ✔ OK" if res.kx <= res.kx_lim else "  ✘ ULTRAPASSADO")
    print(f"  Braço z          : {res.z:10.2f} cm")
    print(f"  Fcc              : {res.Fcc:10.2f} kN")
    print(SEP)
    print(f"  As calculada     : {res.As_calc:10.2f} cm²")
    print(f"  As mínima        : {res.As_min:10.2f} cm²")
    print(f"  As a adotar  ◄── : {res.As_adotar:10.2f} cm²")

    if res.armadura_dupla_necessaria and res.Mrd_lim is not None:
        print(SEP)
        print("  ★ ARMADURA DUPLA ★")
        print(f"  Mrd,lim          : {res.Mrd_lim:10.2f} kN·m")
        print(f"  ΔM               : {res.delta_M:10.2f} kN·m")
        if res.As_linha is not None:
            print(f"  A's (compressão) : {res.As_linha:10.2f} cm²  "
                  f"(d' = {res.d_linha:.1f} cm)")
            print(f"  As adicional     : {res.As_adicional:10.2f} cm²  (tração)")
        else:
            print("  (armadura dupla não foi calculada — ver alertas)")

    if res.secao_insuficiente:
        print(SEP)
        print("  ✘ SEÇÃO INSUFICIENTE — ver alertas abaixo")

    if res.alertas:
        print(SEP)
        print("  ALERTAS:")
        for alerta in res.alertas:
            print(f"  ⚠  {alerta}")

    print(f"{TIT}\n")


# ══════════════════════════════════════════════════════════════════════════════
# 8.  BATERIA DE TESTES
# ══════════════════════════════════════════════════════════════════════════════

def _assert_proximos(val: float, ref: float, tol: float, msg: str) -> None:
    """Verifica se |val − ref| ≤ tol; lança AssertionError com mensagem caso contrário."""
    if abs(val - ref) > tol:
        raise AssertionError(f"{msg}: obtido {val:.4f}, esperado ≈ {ref:.4f} (tol ±{tol})")


def executar_testes() -> None:
    """
    Bateria de testes cobrindo:

        T01 — Viga retangular, M positivo pequeno (kx << kx_lim)
        T02 — Viga retangular, M positivo alto (kx próximo de kx_lim)
        T03 — Viga T, M positivo com LN na mesa (verificar b efetivo)
        T04 — Viga T, M positivo com LN na alma (seção composta)
        T05 — Viga T, M negativo (compressão na alma estreita)
        T06 — Viga I simples, M positivo
        T07 — Viga T + Laje colaborante, M positivo (típico de pontes)
        T08 — Viga I + Laje (ponte), M positivo elevado
        T09 — Retangular + Laje, M positivo
        T10 — Viga retangular, kx > kx_lim → ALERTA sem calcular dupla
        T11 — Viga retangular, kx > kx_lim → CALCULAR armadura dupla
        T12 — Envoltória: mesma seção, M+ e M- (simula longarina de ponte)
        T13 — As calculada < As mínima (momento muito pequeno)
        T14 — Seção insuficiente (momento absurdamente grande)
    """
    PASS = "✔ PASS"
    erros: List[str] = []

    def testar(nome: str, geo: ParametrosGeometricos, Msd: float,
               kx_max: float = 1.0, As_min_ref: float = 0.0,
               dupla: bool = False, calc_dupla: bool = False,
               insuf: bool = False) -> ResultadoDimensionamento:
        res = dimensionar_flexao_simples(geo, Msd, calcular_armadura_dupla=calc_dupla)
        imprimir_resultado(res, titulo=nome)
        falhou = False
        try:
            assert res.As_adotar > 0, "As_adotar deve ser positiva"
            if not insuf:
                assert not res.secao_insuficiente, "Seção não deveria ser insuficiente"
            if kx_max < 1.0:
                assert res.kx <= kx_max + 0.001, (
                    f"kx={res.kx:.4f} deveria ser ≤ {kx_max:.2f}"
                )
            if dupla:
                assert res.armadura_dupla_necessaria, "Deveria exigir armadura dupla"
            if calc_dupla and dupla:
                assert res.As_linha is not None, "A's deveria ter sido calculada"
        except AssertionError as e:
            erros.append(f"[{nome}] {e}")
            falhou = True
        print(f"  → {PASS if not falhou else '✘ FAIL'}\n")
        return res

    print("\n" + "★" * 62)
    print("  BATERIA DE TESTES — dimensionamento_flexao.py")
    print("★" * 62)

    # ── T01: Retangular pequena (kx << kx_lim) ─────────────────────────────
    geo = criar_secao_retangular(bw=30, h=60, d_pos=54, d_neg=54)
    testar("T01 — Retangular, Msd=+120 kN·m", geo, Msd=120.0, kx_max=0.44)

    # ── T02: Retangular, momento alto (kx ≈ 0,40) ─────────────────────────
    geo = criar_secao_retangular(bw=25, h=50, d_pos=44, d_neg=44, fck=25)
    testar("T02 — Retangular, Msd=+230 kN·m (kx alto)", geo, Msd=230.0)

    # ── T03: Viga T com LN na mesa (M positivo moderado) ──────────────────
    # h_alma=120, hf=20, bf=150 → h_total=140
    geo = criar_secao_T(bw=30, h_alma=120, bf=150, hf=20,
                        d_pos=132, d_neg=125, fck=30)
    res = testar("T03 — Viga T, LN na mesa (Msd=+800 kN·m)", geo, Msd=800.0, kx_max=0.44)
    if res.x <= 20:
        print("  ℹ  Linha neutra dentro da mesa (x ≤ hf=20 cm) — como esperado ✔")
    else:
        print(f"  ℹ  Linha neutra na alma (x={res.x:.1f} cm > hf=20 cm)")

    # ── T04: Viga T com LN na alma ─────────────────────────────────────────
    geo = criar_secao_T(bw=30, h_alma=120, bf=80, hf=15,
                        d_pos=128, d_neg=122, fck=30)
    testar("T04 — Viga T, LN na alma (Msd=+1800 kN·m)", geo, Msd=1800.0)

    # ── T05: Viga T, momento negativo (compressão na alma estreita) ────────
    geo = criar_secao_T(bw=30, h_alma=120, bf=150, hf=20,
                        d_pos=132, d_neg=125, fck=30)
    testar("T05 — Viga T, M NEGATIVO (Msd=−800 kN·m)", geo, Msd=-800.0)

    # ── T06: Viga I simples ─────────────────────────────────────────────────
    # bf_inf=40, hf_inf=15, bw=20, h_alma=100, bf_sup=60, hf_sup=20
    geo = criar_secao_I(bw=20, h_alma=100,
                        bf_sup=60, hf_sup=20,
                        bf_inf=40, hf_inf=15,
                        d_pos=127, d_neg=124, fck=35)
    testar("T06 — Viga I, Msd=+1800 kN·m", geo, Msd=1800.0)

    # ── T07: Viga T + Laje colaborante (ponte rodoviária) ──────────────────
    geo = criar_secao_T_com_laje(bw=40, h_viga=100,
                                 b_laje=200, h_laje=15,
                                 d_pos=109, d_neg=108,
                                 fck=30, fyk=500,
                                 ductilidade=ClasseDuctilidade.ESPECIAL)
    testar("T07 — Viga T + Laje, Msd=+3000 kN·m (ponte)", geo, Msd=3000.0,
           kx_max=0.35)  # kx_lim=0,35 para classe especial

    # ── T08: Viga I + Laje (ponte, M positivo elevado) ─────────────────────
    geo = criar_secao_I_com_laje(
        bw=20, h_alma=130,
        bf_inf=60, hf_inf=20,
        b_laje=240, h_laje=20,
        d_pos=162, d_neg=160,
        fck=40, fyk=500,
        ductilidade=ClasseDuctilidade.ESPECIAL,
    )
    testar("T08 — Viga I + Laje (ponte), Msd=+5000 kN·m", geo, Msd=5000.0,
           kx_max=0.35)

    # ── T09: Retangular + Laje ─────────────────────────────────────────────
    geo = criar_secao_retangular_com_laje(bw=35, h_viga=80,
                                          b_laje=150, h_laje=12,
                                          d_pos=85, d_neg=84,
                                          fck=30)
    testar("T09 — Retangular + Laje, Msd=+1200 kN·m", geo, Msd=1200.0)

    # ── T10: Retangular moderada — kx > kx_lim, SEM calcular dupla ─────────
    # Verificação prévia: M_lim(kx=0,45) ≈ 334 kN·m para esta seção.
    # Msd = 380 kN·m → kx ≈ 0,53 > 0,45, mas seção física suporta (M_max ≈ 568 kN·m).
    geo = criar_secao_retangular(bw=25, h=55, d_pos=50, d_neg=50, fck=30)
    testar("T10 — Retangular, kx > kx_lim, só alerta (Msd=+380 kN·m)",
           geo, Msd=380.0, dupla=True, calc_dupla=False)

    # ── T11: Mesma seção — kx > kx_lim, CALCULANDO armadura dupla ─────────
    testar("T11 — Retangular, kx > kx_lim, CALCULAR dupla (Msd=+380 kN·m)",
           geo, Msd=380.0, dupla=True, calc_dupla=True)

    # ── T12: Envoltória (mesma longarina, M+ e M-) ─────────────────────────
    geo_long = criar_secao_T_com_laje(bw=40, h_viga=100,
                                      b_laje=180, h_laje=16,
                                      d_pos=109, d_neg=107,
                                      fck=35, fyk=500,
                                      ductilidade=ClasseDuctilidade.ESPECIAL)
    print("  ── Envoltória: mesmo vão, dois momentos ──")
    r_pos = testar("T12a — Longarina, Msd=+2100 kN·m (M_max)",
                   geo_long, Msd=+2100.0, kx_max=0.35)
    r_neg = testar("T12b — Longarina, Msd=−900 kN·m (M_min)",
                   geo_long, Msd=-900.0)
    print(
        f"  ── Resumo envoltória: As_inf (tração M+) = {r_pos.As_adotar:.2f} cm²  |  "
        f"As_sup (tração M-) = {r_neg.As_adotar:.2f} cm²"
    )

    # ── T13: Momento pequeno → armadura mínima governa ─────────────────────
    geo = criar_secao_retangular(bw=30, h=60, d_pos=54, d_neg=54)
    res = dimensionar_flexao_simples(geo, Msd=20.0)
    imprimir_resultado(res, titulo="T13 — Momento pequeno, As_min governa")
    if res.As_adotar == res.As_min:
        print(f"  ✔  As_min = {res.As_min:.2f} cm² governa corretamente.\n")
    else:
        erros.append("T13: As_min deveria governar")

    # ── T14: Seção insuficiente ────────────────────────────────────────────
    geo = criar_secao_retangular(bw=15, h=30, d_pos=25, d_neg=25, fck=20)
    res = dimensionar_flexao_simples(geo, Msd=900.0)
    imprimir_resultado(res, titulo="T14 — Seção insuficiente (Msd absurdo)")
    if res.secao_insuficiente:
        print("  ✔  Flag secao_insuficiente ativada corretamente.\n")
    else:
        erros.append("T14: deveria marcar secao_insuficiente")

    # ── Sumário ───────────────────────────────────────────────────────────
    print("★" * 62)
    if not erros:
        print("  ✔  TODOS OS TESTES PASSARAM")
    else:
        print(f"  ✘  {len(erros)} TESTE(S) COM FALHA:")
        for e in erros:
            print(f"     • {e}")
    print("★" * 62 + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# 9.  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    executar_testes()
