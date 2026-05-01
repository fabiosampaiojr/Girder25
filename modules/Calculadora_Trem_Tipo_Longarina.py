"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║        Calculadora_Trem_Tipo_Longarina.py                                      ║
║        Módulo de Distribuição Transversal — Método de Engesser-Courbon          ║
╚══════════════════════════════════════════════════════════════════════════════════╝

LÓGICA GERAL
============
1. MÉTODO DE COURBON
   Admite-se que a seção transversal se comporta como um corpo rígido sobre
   apoios elásticos (as longarinas), todos com igual rigidez EI.
   O coeficiente de distribuição transversal η_ij representa a fração de uma
   carga unitária aplicada na posição transversal xj que é absorvida pela
   longarina i:

       η_ij(xj) = 1/n  +  (xi · xj) / Σxi²

   onde xi é a coordenada da longarina i em relação ao centro elástico x0
   (positivo para a direita, negativo para a esquerda).

   A linha de influência (LI) de η_ij é linear em xj:
       η_ij(xj) = coef_lin  +  coef_ang · xj
       coef_lin = 1/n
       coef_ang = xi / Σxi²

2. SEÇÃO AA — carga distribuída q1
   Para a análise de momento máximo no vão, toda a zona rolável com η > 0
   é carregada pelo carregamento distribuído q [kN/m]:

       q1_i = q · ∫_{zona rolável, η>0} η(xj) dxj
            + p' · ∫_{passeios, η>0} η(xj) dxj        [kN/m]

   A integração é analítica (η linear ⇒ primitiva de grau 2).

3. SEÇÃO BB — veículo + carga distribuída (q2 + Q1)
   Para a análise de esforço cortante junto ao apoio, o veículo tipo é
   posicionado transversalmente na posição que maximiza (q2 + Q1):

       Q1_i   = Q · [η(x_veh + 0.5) + η(x_veh + 2.5)]         [kN]
       q2_i   = q · ∫_{zona rolável fora do veículo, η>0} η dxj
              + p' · ∫_{passeios, η>0} η dxj                    [kN/m]

   O veículo ocupa o envelope transversal [x_veh, x_veh + 3.0m].
   As cargas Q estão a 0.5m e 2.5m do início do veículo.
   A varredura é numérica (8 000 pontos) para encontrar x_veh ótimo.

4. CONFIGURAÇÃO CRÍTICA
   A longarina crítica é aquela que apresenta maior valor de (q1 + q2 + Q).

SAÍDAS
======
• get_tabela_resumo()    → lista de listas com cabeçalho
  Colunas: i | xi [m] | xi² [m²] | equação η_ij | q1 [kN/m] | q2 [kN/m] | Q [kN]

• get_resumo_calculo()   → lista de listas com cabeçalho
  Colunas (sem passeio): i | ∫η(x)dx_q1 | q1 | ∫η(x)dx_q2 | q2 | η(x_Q1) | η(x_Q2) | Q
  Colunas (com passeio): acrescenta ∫η(x)dx_p' e q(p') após cada bloco de integral

• get_configuracao_critica() → dict com todos os dados da longarina crítica

VISUALIZAÇÕES (tema dark)
=========================
• plotar_li(i)         → LI com equação e marcações das longarinas
• plotar_secao_AA(i)   → LI + área de carregamento q1
• plotar_secao_BB(i)   → LI + posição ótima do veículo + áreas q2 e Q
• plotar_todas_lis()   → retorna lista de figuras para todas as longarinas
"""

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from typing import List, Tuple, Optional, Dict, Any

# ─── Importações das classes de dados (ajuste o import ao seu projeto) ─────────
# from Gerenciador_Dados import SecaoTransversalSuperestrutura, SecaoTransversal


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TEMA DARK — PALETA DE CORES                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

DARK: Dict[str, str] = {
    "bg":           "#1e1e2e",   # fundo da figure
    "axes_bg":      "#24273a",   # fundo das axes
    "fg":           "#cdd6f4",   # texto, eixos, ticks
    "grid":         "#494d64",   # linhas de grade
    "spine":        "#494d64",   # bordas das axes

    # Elementos da LI e carregamentos
    "li_line":      "#89b4fa",   # linha de influência principal (azul)
    "fill_q1":      "#89b4fa",   # área q1 (azul claro)
    "fill_q2":      "#fab387",   # área q2 (laranja)
    "fill_Q":       "#f38ba8",   # pontos/linhas de Q (vermelho/rosa)
    "fill_passeio": "#a6e3a1",   # área de passeio (verde)
    "veh_fill":     "#f38ba8",   # envelope do veículo (vermelho translúcido)
    "zero_line":    "#585b70",   # linha y = 0

    # Estrutura da seção transversal
    "struct_fill":  "#45475a",   # laje e longarinas
    "struct_edge":  "#cdd6f4",   # contorno da estrutura
    "asfalto":      "#313244",   # camada de asfalto
    "nj_fill":      "#6c7086",   # barreira New Jersey
    "nj_edge":      "#a6adc8",   # contorno da NJ
    "guideline":    "#585b70",   # linhas guia (NJ, eixos)

    # Acentos e anotações
    "accent":       "#cba6f7",   # cor de destaque (roxo)
    "accent2":      "#f9e2af",   # destaque secundário (amarelo)
    "longarina_mk": "#89dceb",   # marcadores das longarinas (ciano)
}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  CONSTANTES DO VEÍCULO TIPO (NBR 7188:2013)                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

VEH_COMPRIMENTO_M: float = 3.00
"""Largura do envelope transversal do veículo tipo [m] (3 m = 300 cm)."""

VEH_POS_RODAS_M: List[float] = [0.50, 2.50]
"""Posições transversais das cargas concentradas dentro do envelope [m]."""

NJ_LARGURA_CM: float = 40.0
"""Largura da barreira New Jersey [cm]."""


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  CALCULADORA PRINCIPAL                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class Calculadora_Trem_Tipo_Longarina:
    """
    Calcula o trem-tipo longitudinal para longarinas pelo Método de Engesser-Courbon.

    Parâmetros
    ----------
    secao_superestrutura : SecaoTransversalSuperestrutura
        Objeto com:
          n_longarinas  [int]   — número de longarinas
          d_extremidade [float] — distância da borda ao eixo da 1ª longarina [cm]
          largura_total [float] — largura total do tabuleiro [cm]

    secao_transversal : SecaoTransversal
        Objeto com:
          classe  [str]           — classe da via ("I - A", "II", etc.)
          passeio [float | False] — largura do passeio [cm] ou False
          h_borda [float]         — espessura do pavimento na borda [cm]
          h_centro[float]         — espessura do pavimento no centro [cm]

    trem_tipo : tuple (Q, q)
        Q [kN]   — carga concentrada por ponto de aplicação (por roda/eixo)
        q [kN/m] — intensidade da carga distribuída de multidão por unidade de
                   largura transversal

    p_linha : float
        Carga de multidão nos passeios [kN/m] (padrão = 0.0).
    """

    # Mapeamento de classes (NBR 7188:2013) — dimensões em METROS
    MAPA_CLASSES: Dict[str, Dict[str, Any]] = {
        "0":     {"faixa": 3.75, "ac_ext": 3.00, "ac_int": 0.60, "pista_dupla": True},
        "I - A": {"faixa": 3.60, "ac_ext": 3.00, "ac_int": 0.60, "pista_dupla": True},
        "I - B": {"faixa": 3.50, "ac_ext": 2.50, "ac_int": 0.00, "pista_dupla": False},
        "II":    {"faixa": 3.50, "ac_ext": 2.50, "ac_int": 0.00, "pista_dupla": False},
        "III":   {"faixa": 3.50, "ac_ext": 1.50, "ac_int": 0.00, "pista_dupla": False},
        "IV":    {"faixa": 3.00, "ac_ext": 1.50, "ac_int": 0.00, "pista_dupla": False},
    }

    def __init__(self,
                 secao_superestrutura,
                 secao_transversal,
                 trem_tipo: Tuple[float, float],
                 p_linha: float = 0.0):

        # ── Referências aos objetos de entrada ──────────────────────────────
        self.ss = secao_superestrutura
        self.st = secao_transversal
        self.Q_kN, self.q_kNm = trem_tipo   # carga concentrada e distribuída
        self.p_linha = p_linha               # carga no passeio

        # ── Geometria em METROS ─────────────────────────────────────────────
        self.n          = int(self.ss.n_longarinas)
        self.L_total_m  = float(self.ss.largura_total) / 100.0
        self.d_ext_m    = float(self.ss.d_extremidade) / 100.0
        # [Ajuste] Removidas as linhas que tentavam acessar atributos inexistentes
        # (bw_longarina, h_longarina, h_laje). Esses parâmetros não são utilizados
        # pelo método de Engesser-Courbon, que só depende das posições das longarinas.
        self.p_m        = float(self.st.passeio) / 100.0 if self.st.passeio else 0.0
        self.h_borda_m  = float(self.st.h_borda) / 100.0
        self.h_centro_m = float(self.st.h_centro) / 100.0

        # Distância entre eixos calculada pela largura total
        if self.n > 1:
            self.d_eixos_m = (self.L_total_m - 2.0 * self.d_ext_m) / (self.n - 1)
        else:
            self.d_eixos_m = 0.0

        # ── Resultados (preenchidos por calcular()) ─────────────────────────
        # Coordenadas transversais (relativas ao centro elástico x0)
        self._xi_m:    List[float] = []
        self._xi2_m:   List[float] = []
        self._sum_xi2: float       = 0.0

        # Coeficientes da LI:  η(xj) = coef_lin + coef_ang · xj
        self._coef_lin: List[float] = []
        self._coef_ang: List[float] = []

        # Limites da zona rolável e passeios (coords relativas a x0)
        self._x_min_m:        float                     = 0.0
        self._x_max_m:        float                     = 0.0
        self._regioes_passeio: List[Tuple[float, float]] = []

        # Resultados dos carregamentos
        self._q1:      List[float]               = []
        self._q2:      List[float]               = []
        self._Q1:      List[float]               = []
        self._x_crit:  List[float]               = []   # posição transversal ótima do veículo
        self._int_q1:  List[float]               = []   # ∫η para q1 (zona central)
        self._int_q2:  List[float]               = []   # ∫η para q2 (zona central fora veículo)
        self._y_Q:     List[Tuple[float, float]] = []   # (η(x_Q1), η(x_Q2))

        # ── [NOVO] Integrais de passeio armazenadas separadamente ───────────
        # Permitem exibição como colunas independentes em get_resumo_calculo()
        # e montagem da anotação nas funções de plot.
        self._int_passeio_q1: List[float] = []  # ∫η(x)dx nos passeios (seção AA)
        self._int_passeio_q2: List[float] = []  # ∫η(x)dx nos passeios (seção BB — mesma região, independente do veículo)

        # Executa o cálculo
        self.calcular()

    # ══════════════════════════════════════════════════════════════════════════
    #  PASSO 1 — Coordenadas xi das longarinas relativas ao centro elástico
    # ══════════════════════════════════════════════════════════════════════════
    def _calcular_coordenadas(self) -> None:
        """
        Calcula xi = xi_abs - x0  para cada longarina i.

        Posição absoluta:  xi_abs = d_ext + (i-1) · d_eixos    [m]
        Centro elástico:   x0     = L_total / 2                 [m]
        Coordenada relativa: xi   = xi_abs - x0                 [m]

        Convenção: xi > 0 → direita do centro; xi < 0 → esquerda.
        """
        x0 = self.L_total_m / 2.0
        for i in range(1, self.n + 1):
            xi_abs = self.d_ext_m + (i - 1) * self.d_eixos_m
            xi     = xi_abs - x0
            self._xi_m.append(xi)
            self._xi2_m.append(xi ** 2)
        self._sum_xi2 = sum(self._xi2_m)

    # ══════════════════════════════════════════════════════════════════════════
    #  PASSO 2 — Coeficientes da Linha de Influência de Courbon
    # ══════════════════════════════════════════════════════════════════════════
    def _calcular_coeficientes_li(self) -> None:
        """
        Coeficiente de distribuição transversal:
            η_ij(xj) = 1/n  +  (xi · xj) / Σxi²
                     = coef_lin  +  coef_ang · xj

            coef_lin = 1/n
            coef_ang = xi / Σxi²   (= 0 se Σxi² = 0, i.e. apenas 1 longarina)

        Para longarina sobre o centro elástico (xi = 0): coef_ang = 0  →  η = 1/n (constante).
        """
        for xi in self._xi_m:
            self._coef_lin.append(1.0 / self.n)
            ang = xi / self._sum_xi2 if abs(self._sum_xi2) > 1e-15 else 0.0
            self._coef_ang.append(ang)

    # ══════════════════════════════════════════════════════════════════════════
    #  PASSO 3 — Delimitação das zonas de carregamento
    # ══════════════════════════════════════════════════════════════════════════
    def _calcular_regioes(self) -> None:
        """
        Determina, em coordenadas relativas ao centro elástico (x0 = L/2):

        • Zona rolável [x_min, x_max]: região entre as faces internas das
          barreiras NJ. Veículos só podem ser posicionados nesta faixa.

        • Regiões de passeio [(a0, b0), (a1, b1), ...]: faixas onde atua
          a carga p_linha (se houver passeio).

        Cálculo das faces das NJs em coords absolutas:
          Face externa NJ esq.  = p
          Face interna NJ esq.  = p + 40 cm = p_m + 0.40 m
          Face interna NJ dir.  = L_total - p_dir - 0.40 m
          Face externa NJ dir.  = L_total - p_dir
          onde p_dir = p (pista simples) ou 0 (pista dupla)
        """
        nj_m = NJ_LARGURA_CM / 100.0   # 0.40 m

        _config_cm = self.st.obter_config_via()
        if not _config_cm:
            raise ValueError(f"Classe de via desconhecida: '{self.st.classe}'")
        # Converte de cm para metros (a calculadora trabalha em metros)
        config = {
            "faixa":       _config_cm["faixa"]  / 100.0,
            "ac_ext":      _config_cm["ac_ext"] / 100.0,
            "ac_int":      _config_cm["ac_int"] / 100.0,
            "pista_dupla": _config_cm["pista_dupla"],
        }

        dupla  = config.get("pista_dupla", False)
        p_dir  = self.p_m if (self.p_m > 0 and not dupla) else 0.0

        x0 = self.L_total_m / 2.0

        # Faces internas das NJs em coords absolutas
        nj_esq_int = self.p_m + nj_m
        nj_dir_int = self.L_total_m - p_dir - nj_m

        # Zona rolável em coords relativas
        self._x_min_m = nj_esq_int - x0
        self._x_max_m = nj_dir_int - x0

        # Passeios em coords relativas
        if self.p_m > 0:
            # Passeio esquerdo (sempre presente quando p > 0)
            self._regioes_passeio.append((-x0, -x0 + self.p_m))
            if not dupla:
                # Passeio direito (pista simples)
                self._regioes_passeio.append((x0 - self.p_m, x0))

    # ══════════════════════════════════════════════════════════════════════════
    #  AUXILIAR — Integral analítica de η positivo em [a, b]
    # ══════════════════════════════════════════════════════════════════════════
    @staticmethod
    def _integral_li_positiva(a: float, b: float,
                               c0: float, c1: float) -> float:
        """
        Calcula analiticamente ∫_{a}^{b} max(η(x), 0) dx  para η linear.

        η(x) = c0 + c1·x
        Primitiva: F(x) = c0·x + (c1/2)·x²

        O zero de η está em x_zero = -c0/c1  (se c1 ≠ 0).

        Estratégia baseada no SINAL de c1 (direção da função):

          • c1 > 0 (crescente): η > 0 para x > x_zero.
            A região positiva começa em max(x_zero, a) e vai até b.

          • c1 < 0 (decrescente): η > 0 para x < x_zero.
            A região positiva vai de a até min(x_zero, b).

        NOTA SOBRE A CORREÇÃO (rev. 2025):
        ─────────────────────────────────
        A lógica anterior baseada em η(a) era incorreta para o caso:
            c1 > 0  E  x_zero < a   (zero à esquerda do intervalo)
        Nesse cenário η(a) > 0 e a função é positiva em todo [a, b],
        mas o código retornava 0 porque x_fim = min(x_zero, b) = x_zero < a.
        A versão corrigida usa a direção de c1 como critério, eliminando
        completamente essa ambiguidade e garantindo simetria dos resultados
        para estruturas simétricas (L1↔Ln, L2↔L(n-1), etc.).
        """
        if a >= b:
            return 0.0

        def F(x: float) -> float:
            return c0 * x + 0.5 * c1 * x ** 2

        # ── Caso constante (c1 ≈ 0) ─────────────────────────────────────────
        if abs(c1) < 1e-15:
            return max(0.0, c0) * (b - a)

        # ── Zero da LI ───────────────────────────────────────────────────────
        x_zero = -c0 / c1

        if c1 > 0:
            # Função crescente: η > 0 para x > x_zero
            # A parte positiva começa em max(x_zero, a) e vai até b
            x_start = max(x_zero, a)
            if x_start >= b:
                return 0.0          # intervalo inteiro negativo
            return F(b) - F(x_start)
        else:
            # Função decrescente: η > 0 para x < x_zero
            # A parte positiva vai de a até min(x_zero, b)
            x_end = min(x_zero, b)
            if x_end <= a:
                return 0.0          # intervalo inteiro negativo
            return F(x_end) - F(a)

    # ══════════════════════════════════════════════════════════════════════════
    #  PASSO 4 — Seção AA: carga distribuída q1
    # ══════════════════════════════════════════════════════════════════════════
    def _calcular_secao_AA(self) -> None:
        """
        q1_i = q · ∫_{zona rolável, η>0} η(xj) dxj
             + p' · ∫_{passeios, η>0} η(xj) dxj       [kN/m]

        Corresponde à seção de máximo momento positivo (meio do vão).
        Toda a zona rolável com ordenada positiva é carregada por q.

        A integral dos passeios é calculada e armazenada separadamente em
        self._int_passeio_q1 para permitir exibição detalhada na tabela e
        nas anotações dos gráficos.
        """
        for k in range(self.n):
            c0, c1 = self._coef_lin[k], self._coef_ang[k]

            # Integral na zona rolável (somente η > 0)
            int_central = self._integral_li_positiva(
                self._x_min_m, self._x_max_m, c0, c1
            )

            # ── [AJUSTE] Integral nos passeios armazenada individualmente ──
            # A integral de cada região de passeio é somada e guardada em
            # self._int_passeio_q1[k] para uso em tabelas e anotações.
            int_passeio = sum(
                self._integral_li_positiva(a, b, c0, c1)
                for a, b in self._regioes_passeio
            )
            self._int_passeio_q1.append(int_passeio)
            # ────────────────────────────────────────────────────────────────

            q1_total = self.q_kNm * int_central + self.p_linha * int_passeio
            self._q1.append(q1_total)
            self._int_q1.append(int_central)   # guarda apenas parte central

    # ══════════════════════════════════════════════════════════════════════════
    #  PASSO 5 — Seção BB: veículo posicionado para máximo (q2 + Q1)
    # ══════════════════════════════════════════════════════════════════════════
    def _calcular_secao_BB(self, n_pontos: int = 8000) -> None:
        """
        Varre posições transversais x_veh ∈ [x_min, x_max - 3m] do veículo
        e encontra aquela que maximiza (q2 + Q1):

          Q1(x_veh) = Q · [ η(x_veh+0.5) + η(x_veh+2.5) ]
          q2(x_veh) = q · { ∫_{x_min}^{x_veh}      max(η,0) dx
                           + ∫_{x_veh+3}^{x_max}    max(η,0) dx }
                    + p' · ∫_{passeios, η>0} η dx

        Seção BB corresponde ao máximo esforço cortante (seção próxima ao apoio).

        A integral dos passeios é independente da posição do veículo (os passeios
        ficam fora da zona rolável, não são afetados pelo envelope do veículo) e
        é armazenada separadamente em self._int_passeio_q2.
        """
        veh_L   = VEH_COMPRIMENTO_M          # 3.0 m
        pos_Q   = VEH_POS_RODAS_M            # [0.5, 2.5] m

        for k in range(self.n):
            c0, c1 = self._coef_lin[k], self._coef_ang[k]

            # ── [AJUSTE] Integral nos passeios armazenada individualmente ──
            # Independe da posição do veículo: os passeios estão sempre fora
            # da zona rolável. É calculada uma única vez por longarina e
            # reutilizada em toda a varredura de x_veh.
            int_passeio = sum(
                self._integral_li_positiva(a, b, c0, c1)
                for a, b in self._regioes_passeio
            )
            self._int_passeio_q2.append(int_passeio)
            # ────────────────────────────────────────────────────────────────
            contrib_passeio = self.p_linha * int_passeio

            # Varredura numérica das posições do veículo
            x_veh_min_val = self._x_min_m
            x_veh_max_val = self._x_max_m - veh_L

            # Verificação: se o veículo não cabe na zona rolável, retorna zeros
            if x_veh_max_val < x_veh_min_val:
                self._q2.append(contrib_passeio)
                self._Q1.append(0.0)
                self._x_crit.append(x_veh_min_val)
                self._int_q2.append(0.0)
                self._y_Q.append((0.0, 0.0))
                continue

            x_veh_vals = np.linspace(x_veh_min_val, x_veh_max_val, n_pontos)

            melhor_efeito = -np.inf
            melhor_x      = x_veh_min_val
            melhor_q2     = 0.0
            melhor_Q1     = 0.0
            melhor_y_Q    = (0.0, 0.0)
            melhor_int_q2 = 0.0

            for x_veh in x_veh_vals:
                # ── Cargas concentradas: η nas posições das rodas ───────────
                y_roda = [c0 + c1 * (x_veh + p) for p in pos_Q]
                Q1 = self.Q_kN * sum(y_roda)

                # ── Carga distribuída: zona rolável excluindo envelope ───────
                int_antes  = self._integral_li_positiva(
                    self._x_min_m, x_veh, c0, c1
                )
                int_depois = self._integral_li_positiva(
                    x_veh + veh_L, self._x_max_m, c0, c1
                )
                int_q2_central = int_antes + int_depois
                q2 = self.q_kNm * int_q2_central + contrib_passeio

                efeito = q2 + Q1
                if efeito > melhor_efeito:
                    melhor_efeito = efeito
                    melhor_x      = x_veh
                    melhor_q2     = q2
                    melhor_Q1     = Q1
                    melhor_y_Q    = tuple(y_roda)
                    melhor_int_q2 = int_q2_central

            self._q2.append(melhor_q2)
            self._Q1.append(melhor_Q1)
            self._x_crit.append(melhor_x)
            self._y_Q.append(melhor_y_Q)
            self._int_q2.append(melhor_int_q2)

    # ══════════════════════════════════════════════════════════════════════════
    #  MÉTODO PRINCIPAL — Executa todos os passos em ordem
    # ══════════════════════════════════════════════════════════════════════════
    def calcular(self) -> None:
        """Executa o cálculo completo (chamado automaticamente no __init__)."""
        self._calcular_coordenadas()
        self._calcular_coeficientes_li()
        self._calcular_regioes()
        self._calcular_secao_AA()
        self._calcular_secao_BB()

    # ══════════════════════════════════════════════════════════════════════════
    #  FORMATAÇÃO DA EQUAÇÃO η_ij
    # ══════════════════════════════════════════════════════════════════════════
    def _formatar_equacao(self, k: int) -> str:
        """
        Retorna string formatada da equação da LI para a longarina k (0-indexed).
        Exemplo: "η(x) = 0.2000 - 0.07143·x"
        """
        c0 = self._coef_lin[k]
        c1 = self._coef_ang[k]
        sinal = "+" if c1 >= 0 else "-"
        return f"η(x) = {c0:.4f} {sinal} {abs(c1):.5f}·x"

    # ══════════════════════════════════════════════════════════════════════════
    #  SAÍDAS TABULARES
    # ══════════════════════════════════════════════════════════════════════════
    def get_tabela_resumo(self) -> List[List]:
        """
        Retorna lista de listas com resumo por longarina.
        A primeira sublista é o cabeçalho.

        Colunas
        -------
        i          — número da longarina (1-indexed)
        xi [m]     — coordenada transversal relativa ao centro elástico
        xi² [m²]   — quadrado da coordenada
        η_ij       — equação da linha de influência como string
        q1 [kN/m]  — carga distribuída equivalente (seção AA)
        q2 [kN/m]  — carga distribuída equivalente (seção BB)
        Q [kN]     — carga concentrada equivalente (seção BB)
        """
        cabecalho = ["i", "xi [m]", "xi² [m²]", "η_ij", "q1 [kN/m]", "q2 [kN/m]", "Q [kN]"]
        tabela = [cabecalho]
        for k in range(self.n):
            tabela.append([
                k + 1,
                float(round(self._xi_m[k],   4)),
                float(round(self._xi2_m[k],  4)),
                self._formatar_equacao(k),
                float(round(self._q1[k],     3)),   # alterado para 3 casas
                float(round(self._q2[k],     3)),   # alterado para 3 casas
                float(round(self._Q1[k],     3)),   # alterado para 3 casas
            ])
        return tabela

    def get_resumo_calculo(self) -> List[List]:
        """
        Retorna lista de listas com o detalhamento numérico do cálculo.
        A primeira sublista é o cabeçalho.

        Colunas (sem passeio)
        ---------------------
        i | ∫η(x)dx_q1 | q1 | ∫η(x)dx_q2 | q2 | η(x_Q1) | η(x_Q2) | Q

        Colunas adicionais (com passeio, p' > 0)
        ----------------------------------------
        Após ∫η(x)dx_q1: acrescenta ∫η(x)dx_p'(AA) e q(p')(AA)
        Após ∫η(x)dx_q2: acrescenta ∫η(x)dx_p'(BB) e q(p')(BB)

        A separação das integrais de passeio em colunas próprias permite
        verificação transparente da parcela p' no cálculo de q1 e q2.
        """
        # ── [AJUSTE] Cabeçalho dinâmico conforme presença de passeio ────────
        tem_passeio = self.p_linha > 0.0 and len(self._regioes_passeio) > 0

        if tem_passeio:
            cabecalho = [
                "i",
                "∫η(x)dx_q1 [m]", "∫η(x)dx_p'(AA) [m]", "q(p')(AA) [kN/m]", "q1 [kN/m]",
                "∫η(x)dx_q2 [m]", "∫η(x)dx_p'(BB) [m]", "q(p')(BB) [kN/m]", "q2 [kN/m]",
                "η(x_Q1)", "η(x_Q2)",
                "Q [kN]",
            ]
        else:
            cabecalho = [
                "i",
                "∫η(x)dx_q1 [m]", "q1 [kN/m]",
                "∫η(x)dx_q2 [m]", "q2 [kN/m]",
                "η(x_Q1)", "η(x_Q2)",
                "Q [kN]",
            ]
        # ────────────────────────────────────────────────────────────────────

        tabela = [cabecalho]
        for k in range(self.n):
            y1, y2 = self._y_Q[k]
            if tem_passeio:
                int_p_aa = self._int_passeio_q1[k]
                int_p_bb = self._int_passeio_q2[k]
                q_p_aa   = float(round(self.p_linha * int_p_aa, 3))   # alterado para 3 casas
                q_p_bb   = float(round(self.p_linha * int_p_bb, 3))   # alterado para 3 casas
                tabela.append([
                    k + 1,
                    float(round(self._int_q1[k],   5)),
                    float(round(int_p_aa,           5)),
                    q_p_aa,
                    float(round(self._q1[k],        3)),   # alterado para 3 casas
                    float(round(self._int_q2[k],    5)),
                    float(round(int_p_bb,           5)),
                    q_p_bb,
                    float(round(self._q2[k],        3)),   # alterado para 3 casas
                    float(round(y1,                 5)),
                    float(round(y2,                 5)),
                    float(round(self._Q1[k],        3)),   # alterado para 3 casas
                ])
            else:
                tabela.append([
                    k + 1,
                    float(round(self._int_q1[k], 5)),
                    float(round(self._q1[k],     3)),      # alterado para 3 casas
                    float(round(self._int_q2[k], 5)),
                    float(round(self._q2[k],     3)),      # alterado para 3 casas
                    float(round(y1,              5)),
                    float(round(y2,              5)),
                    float(round(self._Q1[k],     3)),      # alterado para 3 casas
                ])
        return tabela

    def get_configuracao_critica(self) -> Dict[str, Any]:
        """
        Retorna dicionário com os dados da longarina mais solicitada.
        Critério: maior valor de (q1 + q2 + Q).

        Chaves do dicionário
        --------------------
        longarina    — número da longarina crítica (1-indexed)
        xi_m         — coordenada transversal [m]
        xi2_m2       — xi² [m²]
        sum_xi2_m2   — Σxi² [m²]
        equacao_li   — equação η_ij como string
        q1_kNm       — carga distribuída seção AA [kN/m]
        q2_kNm       — carga distribuída seção BB [kN/m]
        Q_kN         — carga concentrada seção BB [kN]
        total        — q1 + q2 + Q [misto, apenas para comparação]
        x_critico_m  — posição transversal ótima do veículo [m]
        """
        totais  = [self._q1[k] + self._q2[k] + self._Q1[k] for k in range(self.n)]
        k_crit  = int(np.argmax(totais))
        return {
            "longarina":   k_crit + 1,
            "xi_m":        float(round(self._xi_m[k_crit],   4)),
            "xi2_m2":      float(round(self._xi2_m[k_crit],  4)),
            "sum_xi2_m2":  float(round(self._sum_xi2,         4)),
            "equacao_li":  self._formatar_equacao(k_crit),
            "q1_kNm":      float(round(self._q1[k_crit],      3)),   # alterado para 3 casas
            "q2_kNm":      float(round(self._q2[k_crit],      3)),   # alterado para 3 casas
            "Q_kN":        float(round(self._Q1[k_crit],       3)),   # alterado para 3 casas
            "total":       float(round(totais[k_crit],          3)),   # alterado para 3 casas
            "x_critico_m": float(round(self._x_crit[k_crit],   4)),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  UTILITÁRIOS DE VISUALIZAÇÃO (tema dark)
    # ══════════════════════════════════════════════════════════════════════════
    @staticmethod
    def _aplicar_tema_dark(fig: plt.Figure, axes: List[plt.Axes]) -> None:
        """Aplica o tema dark de forma uniforme a uma figure e seus axes."""
        fig.patch.set_facecolor(DARK["bg"])
        for ax in axes:
            ax.set_facecolor(DARK["axes_bg"])
            ax.tick_params(colors=DARK["fg"], which="both")
            ax.xaxis.label.set_color(DARK["fg"])
            ax.yaxis.label.set_color(DARK["fg"])
            ax.title.set_color(DARK["fg"])
            for spine in ax.spines.values():
                spine.set_edgecolor(DARK["spine"])
            ax.grid(True, color=DARK["grid"], alpha=0.35, linestyle="--", linewidth=0.7)

    def _anotacao_resultado(self, ax: plt.Axes, texto: str,
                            x: float = 0.01, y: float = 0.97) -> None:
        """Insere uma caixa de texto com resultado no canto superior esquerdo do axes."""
        ax.text(x, y, texto, transform=ax.transAxes,
                ha="left", va="top", fontsize=8.5, color=DARK["fg"],
                family="monospace",
                bbox=dict(fc=DARK["axes_bg"], ec=DARK["spine"], alpha=0.88, pad=5))

    def _desenhar_bordas_nj(self, ax: plt.Axes) -> None:
        """Desenha as linhas verticais indicando as faces internas dos NJs."""
        for x_nj, label in [(self._x_min_m, "NJ ←"), (self._x_max_m, "NJ →")]:
            ax.axvline(x_nj, color=DARK["nj_edge"], linewidth=1.0,
                       linestyle=":", alpha=0.75)
            ax.text(x_nj, ax.get_ylim()[1] * 0.96, label,
                    ha="center", va="top", fontsize=7.5, color=DARK["nj_edge"], alpha=0.8)

    # ══════════════════════════════════════════════════════════════════════════
    #  AUXILIAR DE PLOTAGEM — Seção transversal esquemática (painel inferior)
    # ══════════════════════════════════════════════════════════════════════════
    def _desenhar_secao_transversal_mini(
        self,
        ax: plt.Axes,
        i_highlight: int,
        x_veh: float = None,
        modo: str = "li",
    ) -> None:
        """
        Desenha uma visão esquemática da seção transversal no eixo ``ax``.

        Coordenadas no mesmo sistema x dos diagramas LI acima (metros,
        relativo ao centro elástico). O eixo compartilha ``sharex`` com o
        painel principal, portanto as longarinas ficam alinhadas com a LI.

        Conteúdo
        --------
        • Laje: retângulo cheio na cota y = 0 … h_laje
        • Longarinas: retângulos abaixo da laje; longarina i_highlight
          em cor de destaque (DARK["fill_Q"])
        • Linhas de eixo traço-ponto em cada longarina
        • Fronteiras NJ (linhas verticais pontilhadas)
        • Zonas de passeio (fill verde translúcido)
        • Zona roulante (fill de fundo)
        • Envelope do veículo para modo 'bb' (fill vermelho + setas das rodas)

        Parâmetros
        ----------
        ax          : Axes alvo (já criado via GridSpec, com sharex ativo)
        i_highlight : índice 1-based da longarina a destacar
        x_veh       : posição transversal inicial do veículo [m] (modo 'bb')
        modo        : 'li' | 'aa' | 'bb'

        Notas
        -----
        • NÃO chama set_xlim — o sharex com o painel superior garante
          alinhamento automático.
        • As alturas (h_laje, h_long) são simbólicas e proporcionais à
          largura total, garantindo boa aparência qualquer que seja a
          geometria real da ponte.
        """
        # ── Tema ──────────────────────────────────────────────────────────────
        ax.set_facecolor(DARK["axes_bg"])
        for sp in ax.spines.values():
            sp.set_edgecolor(DARK["spine"])
            sp.set_linewidth(0.5)

        scale  = self.L_total_m           # base de escala (largura total em m)
        h_laje = scale * 0.040            # espessura simbólica da laje
        h_long = scale * 0.090            # altura simbólica das longarinas
        bw     = max(self.d_eixos_m * 0.28, scale * 0.018)  # largura simbólica

        # ── Zona roulante (fundo suave) ───────────────────────────────────────
        zona_cor = (DARK["fill_q1"]  if modo == "aa"
                    else DARK["fill_q2"] if modo == "bb"
                    else DARK["li_line"])
        ax.axvspan(self._x_min_m, self._x_max_m,
                   color=zona_cor, alpha=0.08, zorder=1)

        # ── Passeios ──────────────────────────────────────────────────────────
        for a, b in self._regioes_passeio:
            ax.add_patch(mpatches.Rectangle(
                (a, 0), b - a, h_laje * 0.55,
                facecolor=DARK["fill_passeio"], edgecolor="none",
                alpha=0.35, zorder=2,
            ))

        # ── Envelope do veículo (modo BB) ─────────────────────────────────────
        if x_veh is not None:
            ax.add_patch(mpatches.Rectangle(
                (x_veh, 0), VEH_COMPRIMENTO_M, h_laje,
                facecolor=DARK["veh_fill"], edgecolor=DARK["fill_Q"],
                alpha=0.30, linewidth=0.9, zorder=4,
            ))
            for pos_r in VEH_POS_RODAS_M:
                xr = x_veh + pos_r
                ax.plot([xr, xr], [-h_long * 0.18, h_laje * 1.15],
                        color=DARK["fill_Q"], lw=1.1, linestyle="-.",
                        alpha=0.75, zorder=5)

        # ── Laje ──────────────────────────────────────────────────────────────
        L2 = self.L_total_m / 2.0
        ax.add_patch(mpatches.Rectangle(
            (-L2, 0), self.L_total_m, h_laje,
            facecolor=DARK["struct_fill"], edgecolor=DARK["struct_edge"],
            linewidth=0.8, zorder=3, alpha=0.90,
        ))

        # ── Longarinas ────────────────────────────────────────────────────────
        for k2, xi in enumerate(self._xi_m):
            is_hl = (k2 + 1 == i_highlight)
            fc = DARK["fill_Q"]       if is_hl else DARK["struct_fill"]
            ec = DARK["fill_Q"]       if is_hl else DARK["struct_edge"]
            lw = 1.7                  if is_hl else 0.7

            ax.add_patch(mpatches.Rectangle(
                (xi - bw / 2, -h_long), bw, h_long,
                facecolor=fc, edgecolor=ec,
                linewidth=lw, zorder=4, alpha=0.92,
            ))
            # Linha de eixo traço-ponto
            ax.plot(
                [xi, xi],
                [-(h_long + h_laje * 0.45), h_laje + h_laje * 0.30],
                color=DARK["guideline"], lw=0.45, ls="-.", alpha=0.35, zorder=2,
            )
            # Rótulo (abaixo da longarina)
            ax.text(
                xi, -(h_long + h_laje * 0.45),
                f"L{k2+1}",
                ha="center", va="top", fontsize=6.5,
                color=DARK["fill_Q"] if is_hl else DARK["fg"],
                fontweight="bold" if is_hl else "normal",
            )

        # ── Fronteiras NJ ─────────────────────────────────────────────────────
        for x_nj in [self._x_min_m, self._x_max_m]:
            ax.axvline(x_nj, color=DARK["nj_edge"], linewidth=0.9,
                       linestyle=":", alpha=0.80, zorder=6)
            ax.text(x_nj, h_laje * 1.20, "NJ",
                    ha="center", va="bottom", fontsize=5.5,
                    color=DARK["nj_edge"], alpha=0.85)

        # ── Interface laje / topo longarina ───────────────────────────────────
        ax.axhline(0, color=DARK["struct_edge"], linewidth=0.5, zorder=3, alpha=0.45)

        # ── Formatação do eixo ────────────────────────────────────────────────
        ax.set_ylim(-(h_long + h_laje * 0.75), h_laje * 1.65)
        ax.set_yticks([])
        ax.set_xlabel("Posição transversal  x  [m]",
                      fontsize=9, color=DARK["fg"], labelpad=3)
        ax.tick_params(axis="x", colors=DARK["fg"], labelsize=8.0,
                       length=3, width=0.6)
        ax.grid(False)
        ax.xaxis.grid(True, color=DARK["grid"], alpha=0.20,
                      linewidth=0.35, linestyle="--")
        ax.set_axisbelow(True)

        # Título do painel
        _titulos = {
            "li":  "Seção Transversal Esquemática",
            "aa":  "Seção Transversal  —  Zona de Carregamento q₁",
            "bb":  "Seção Transversal  —  Posição Ótima do Veículo (BB)",
        }
        ax.set_title(
            f"{_titulos.get(modo, 'Seção Transversal')}"
            f"   ·   Longarina {i_highlight} em destaque",
            fontsize=7.5, color=DARK["fg"], pad=4, loc="left",
        )

    # ──────────────────────────────────────────────────────────────────────────
    #  PLOT 1 — Linha de Influência de Courbon
    # ──────────────────────────────────────────────────────────────────────────
    def plotar_li(self, i: int) -> plt.Figure:
        """
        Plota a linha de influência η_ij para a longarina i (1-indexed).

        Layout em dois painéis (GridSpec 2 × 1):
          [0] Diagrama da LI com fills positivo / negativo, marcadores em
              todas as longarinas, destaque do zero da LI na zona roulante,
              anotações de η nas posições das longarinas.
          [1] Seção transversal esquemática alinhada ao painel superior,
              destacando a longarina i e mostrando a zona roulante e passeios.

        O atributo ``fig.interactive_data`` é preenchido com os dados
        necessários para o canvas interativo (crosshair + tooltip + zoom).

        Parâmetros
        ----------
        i : int
            Número da longarina (1-indexed).

        Retorna
        -------
        matplotlib.figure.Figure
        """
        k   = i - 1
        c0  = self._coef_lin[k]
        c1  = self._coef_ang[k]
        L2  = self.L_total_m / 2.0

        x_plot = np.linspace(-L2, L2, 1200)
        y_plot = c0 + c1 * x_plot

        # ── Figura e GridSpec ─────────────────────────────────────────────────
        # figsize=(9.21, 6.41) → 921×641 px, encaixa no QFrame exato do software.
        fig = plt.figure(figsize=(9.21, 6.41), dpi=100)
        fig.patch.set_facecolor(DARK["bg"])

        gs = GridSpec(
            2, 1, figure=fig,
            height_ratios=[70, 30],
            hspace=0.08,
            left=0.09, right=0.97, top=0.88, bottom=0.10,
        )
        ax_li  = fig.add_subplot(gs[0])
        ax_sec = fig.add_subplot(gs[1], sharex=ax_li)   # alinha x com painel LI

        self._aplicar_tema_dark(fig, [ax_li, ax_sec])

        # ── Título e subtítulo ─────────────────────────────────────────────────
        fig.text(
            0.50, 0.955,
            f"Linha de Influência de Courbon  ·  Longarina {i}",
            ha="center", va="top",
            fontsize=11, fontweight="bold", color=DARK["accent"],
        )
        fig.text(
            0.50, 0.915,
            f"{self._formatar_equacao(k)}"
            f"   |   n = {self.n}"
            f"   |   Σxi² = {self._sum_xi2:.4f} m²",
            ha="center", va="top",
            fontsize=8.5, color=DARK["fg"],
        )

        # ═════════════════════════════════════════════════════════════════════
        #  Painel superior: Linha de Influência
        # ═════════════════════════════════════════════════════════════════════

        # Zona roulante (fundo muito suave)
        ax_li.axvspan(self._x_min_m, self._x_max_m,
                      color=DARK["li_line"], alpha=0.06, zorder=0)

        # Passeios
        for j, (a, b) in enumerate(self._regioes_passeio):
            ax_li.axvspan(a, b, color=DARK["fill_passeio"], alpha=0.10, zorder=0,
                          label="Passeio" if j == 0 else "")

        # Preenchimentos positivo / negativo da LI
        ax_li.fill_between(x_plot, 0, y_plot, where=(y_plot > 0),
                            color=DARK["li_line"], alpha=0.18, zorder=1,
                            linewidth=0)
        ax_li.fill_between(x_plot, 0, y_plot, where=(y_plot < 0),
                            color=DARK["fill_Q"], alpha=0.12, zorder=1,
                            linewidth=0)

        # Curva principal
        ax_li.plot(x_plot, y_plot,
                   color=DARK["li_line"], linewidth=2.4, zorder=4,
                   label=f"$\\eta_{{{i}}}(x)$  =  {self._formatar_equacao(k).split('= ')[1]}")

        # Linha y = 0
        ax_li.axhline(0, color=DARK["zero_line"], linewidth=1.0,
                      linestyle="-", zorder=2)

        # Fronteiras NJ
        for x_nj in [self._x_min_m, self._x_max_m]:
            ax_li.axvline(x_nj, color=DARK["nj_edge"], linewidth=1.0,
                          linestyle=":", alpha=0.82, zorder=5)

        # Marcadores e anotações em cada longarina
        for k2, xi2 in enumerate(self._xi_m):
            y_eta = c0 + c1 * xi2
            is_hl = (k2 == k)
            cor   = DARK["fill_Q"] if is_hl else DARK["accent"]
            ms    = 10 if is_hl else 7

            ax_li.plot(xi2, y_eta, "o", color=cor, markersize=ms, zorder=6,
                       markeredgecolor="white", markeredgewidth=0.5)

            off_y = 22 if y_eta >= 0 else -32
            ax_li.annotate(
                f"L{k2+1}\nx = {xi2:.2f} m\nη = {y_eta:.3f}",
                xy=(xi2, y_eta),
                xytext=(0, off_y),
                textcoords="offset points",
                ha="center", fontsize=7.5,
                color=cor,
                fontweight="bold" if is_hl else "normal",
                arrowprops=dict(arrowstyle="-", color=cor, lw=0.7),
                bbox=dict(
                    boxstyle="round,pad=0.28",
                    facecolor=DARK["bg"], edgecolor=cor,
                    linewidth=0.6, alpha=0.88,
                ),
                zorder=7,
            )

        # Zero da LI dentro da zona roulante
        if abs(c1) > 1e-12:
            x_zero = -c0 / c1
            if self._x_min_m < x_zero < self._x_max_m:
                ax_li.axvline(x_zero, color=DARK["accent2"], linewidth=1.0,
                              linestyle="--", alpha=0.78, zorder=5,
                              label=f"η = 0  em  x = {x_zero:.3f} m")
                ax_li.plot(x_zero, 0, "D", color=DARK["accent2"],
                           markersize=6, zorder=6)

        # Limites e rótulos
        ax_li.set_xlim(-L2 * 1.05, L2 * 1.05)
        y_span = max(y_plot.max() - y_plot.min(), 0.1)
        ax_li.set_ylim(y_plot.min() - 0.22 * y_span,
                       y_plot.max() + 0.22 * y_span)

        ax_li.set_ylabel("η(x)", fontsize=10, color=DARK["fg"])
        ax_li.tick_params(labelbottom=False)    # labels no painel inferior
        ax_li.legend(
            facecolor=DARK["axes_bg"], edgecolor=DARK["spine"],
            labelcolor=DARK["fg"], fontsize=8.0, loc="upper right",
        )

        # ═════════════════════════════════════════════════════════════════════
        #  Painel inferior: Seção transversal esquemática
        # ═════════════════════════════════════════════════════════════════════
        self._desenhar_secao_transversal_mini(ax_sec, i_highlight=i, modo="li")

        # ── Dados para interatividade (lidos por InteractiveLICanvas) ─────────
        fig.interactive_data = {
            "ax":          ax_li,
            "c0":          c0,
            "c1":          c1,
            "x_min":       float(-L2),
            "x_max":       float(L2),
            "x_roul_min":  self._x_min_m,
            "x_roul_max":  self._x_max_m,
            "longarina_i": i,
            "tipo":        "li",
        }

        return fig

    # ──────────────────────────────────────────────────────────────────────────
    #  PLOT 2 — Seção AA (q1)
    # ──────────────────────────────────────────────────────────────────────────
    def plotar_secao_AA(self, i: int, exibir_anotacao: bool = True) -> plt.Figure:
        """
        Plota a seção AA para a longarina i (1-indexed).

        Layout em dois painéis (GridSpec 2 × 1):
          [0] LI η(x) com área de carregamento q1 e passeios preenchidos.
              Anotação técnica com ∫η dx e q1 resultante (controlada por
              ``exibir_anotacao``).
          [1] Seção transversal esquemática com zona de carregamento q1
              destacada e longarina i em destaque.

        Parâmetros
        ----------
        i               : número da longarina (1-indexed)
        exibir_anotacao : exibe caixa de texto com resultados (default True)

        Retorna
        -------
        matplotlib.figure.Figure
        """
        k   = i - 1
        c0  = self._coef_lin[k]
        c1  = self._coef_ang[k]
        L2  = self.L_total_m / 2.0

        x_plot = np.linspace(-L2, L2, 1200)
        y_plot = c0 + c1 * x_plot

        # ── Figura e GridSpec ─────────────────────────────────────────────────
        # figsize=(9.21, 6.41) → 921×641 px
        fig = plt.figure(figsize=(9.21, 6.41), dpi=100)
        fig.patch.set_facecolor(DARK["bg"])

        gs = GridSpec(
            2, 1, figure=fig,
            height_ratios=[70, 30],
            hspace=0.08,
            left=0.09, right=0.97, top=0.88, bottom=0.10,
        )
        ax_aa  = fig.add_subplot(gs[0])
        ax_sec = fig.add_subplot(gs[1], sharex=ax_aa)

        self._aplicar_tema_dark(fig, [ax_aa, ax_sec])

        # ── Título e subtítulo ─────────────────────────────────────────────────
        fig.text(
            0.50, 0.955,
            f"Seção AA  —  Carregamento Distribuído q₁  ·  Longarina {i}",
            ha="center", va="top",
            fontsize=11, fontweight="bold", color=DARK["accent"],
        )
        fig.text(
            0.50, 0.915,
            f"{self._formatar_equacao(k)}"
            f"   |   q = {self.q_kNm} kN/m"
            + (f"   |   p' = {self.p_linha} kN/m" if self.p_linha > 0 else ""),
            ha="center", va="top",
            fontsize=8.5, color=DARK["fg"],
        )

        # ═════════════════════════════════════════════════════════════════════
        #  Painel superior: LI + área q1
        # ═════════════════════════════════════════════════════════════════════

        # Zona roulante (fundo)
        ax_aa.axvspan(self._x_min_m, self._x_max_m,
                      color=DARK["li_line"], alpha=0.05, zorder=0)

        # Passeios
        for j, (a, b) in enumerate(self._regioes_passeio):
            x_p  = np.linspace(a, b, 300)
            y_p  = c0 + c1 * x_p
            mask = y_p > 0
            if np.any(mask):
                ax_aa.fill_between(x_p, 0, y_p, where=mask,
                                   color=DARK["fill_passeio"], alpha=0.42, zorder=2,
                                   label=f"Passeio  p' = {self.p_linha} kN/m" if j == 0 else "")

        # Área q1 (zona roulante, η > 0)
        mask_q = ((x_plot >= self._x_min_m) & (x_plot <= self._x_max_m)
                  & (y_plot > 0))
        ax_aa.fill_between(x_plot, 0, y_plot, where=mask_q,
                           color=DARK["fill_q1"], alpha=0.40, zorder=2,
                           label=f"Área q₁  (q = {self.q_kNm} kN/m)")

        # Curva principal da LI
        ax_aa.plot(x_plot, y_plot,
                   color=DARK["li_line"], linewidth=2.4, zorder=4,
                   label=f"$\\eta_{{{i}}}(x)$")
        ax_aa.axhline(0, color=DARK["zero_line"], linewidth=1.0,
                      linestyle="-", zorder=2)

        # Fronteiras NJ + rótulos
        for x_nj, lbl in [(self._x_min_m, "NJ ←"), (self._x_max_m, "NJ →")]:
            ax_aa.axvline(x_nj, color=DARK["nj_edge"], linewidth=1.0,
                          linestyle=":", alpha=0.82, zorder=5)
            y_lim_top = ax_aa.get_ylim()[1]
            ax_aa.text(x_nj, y_lim_top * 0.96, lbl,
                       ha="center", va="top", fontsize=7.5,
                       color=DARK["nj_edge"], alpha=0.85)

        # ── [AJUSTE] Anotação técnica condicional ─────────────────────────────
        if exibir_anotacao:
            int_val     = self._int_q1[k]
            tem_passeio = self.p_linha > 0.0 and len(self._regioes_passeio) > 0

            if tem_passeio:
                int_p = self._int_passeio_q1[k]
                q_p   = self.p_linha * int_p
                texto = (
                    f"Seção AA  —  Longarina {i}\n"
                    f"η(x) = {self._formatar_equacao(k).split('= ')[1]}\n"
                    f"∫η dx_q1  =  {int_val:.5f} m   →   q·∫ = {self.q_kNm}×{int_val:.5f} = {self.q_kNm*int_val:.3f} kN/m\n"
                    f"∫η dx_p'  =  {int_p:.5f} m   →   p'·∫ = {self.p_linha}×{int_p:.5f} = {q_p:.3f} kN/m\n"
                    f"q1  =  {self.q_kNm*int_val:.3f} + {q_p:.3f}  =  {self._q1[k]:.3f} kN/m"
                )
            else:
                texto = (
                    f"Seção AA  —  Longarina {i}\n"
                    f"η(x) = {self._formatar_equacao(k).split('= ')[1]}\n"
                    f"∫η dx  =  {int_val:.5f} m\n"
                    f"q1  =  {self.q_kNm} × {int_val:.5f}  =  {self._q1[k]:.3f} kN/m"
                )
            self._anotacao_resultado(ax_aa, texto, x=0.01, y=0.99)

        # Limites e rótulos
        ax_aa.set_xlim(-L2 * 1.05, L2 * 1.05)
        y_span = max(y_plot.max() - y_plot.min(), 0.1)
        ax_aa.set_ylim(y_plot.min() - 0.20 * y_span,
                       y_plot.max() + 0.20 * y_span)

        ax_aa.set_ylabel("η(x)", fontsize=10, color=DARK["fg"])
        ax_aa.tick_params(labelbottom=False)
        ax_aa.legend(
            facecolor=DARK["axes_bg"], edgecolor=DARK["spine"],
            labelcolor=DARK["fg"], fontsize=8.5, loc="upper right",
        )

        # ═════════════════════════════════════════════════════════════════════
        #  Painel inferior: Seção transversal esquemática
        # ═════════════════════════════════════════════════════════════════════
        self._desenhar_secao_transversal_mini(ax_sec, i_highlight=i, modo="aa")

        # ── Dados para interatividade ─────────────────────────────────────────
        fig.interactive_data = {
            "ax":          ax_aa,
            "c0":          c0,
            "c1":          c1,
            "x_min":       float(-L2),
            "x_max":       float(L2),
            "x_roul_min":  self._x_min_m,
            "x_roul_max":  self._x_max_m,
            "longarina_i": i,
            "tipo":        "aa",
            "q1":          self._q1[k],
        }

        return fig

    # ──────────────────────────────────────────────────────────────────────────
    #  PLOT 3 — Seção BB (q2 + Q)
    # ──────────────────────────────────────────────────────────────────────────
    def plotar_secao_BB(self, i: int, exibir_anotacao: bool = True) -> plt.Figure:
        """
        Plota a seção BB para a longarina i com o veículo na posição crítica.

        Layout em dois painéis (GridSpec 2 × 1):
          [0] LI η(x) + envelope do veículo + cargas Q + área q2 + passeios.
              Anotação técnica com resultados (controlada por ``exibir_anotacao``).
          [1] Seção transversal esquemática com envelope do veículo posicionado
              e longarina i em destaque.

        Parâmetros
        ----------
        i               : número da longarina (1-indexed)
        exibir_anotacao : exibe caixa de texto com resultados (default True)

        Retorna
        -------
        matplotlib.figure.Figure
        """
        k       = i - 1
        c0      = self._coef_lin[k]
        c1      = self._coef_ang[k]
        x_veh   = self._x_crit[k]
        veh_L   = VEH_COMPRIMENTO_M
        L2      = self.L_total_m / 2.0
        y1, y2  = self._y_Q[k]

        x_plot = np.linspace(-L2, L2, 1200)
        y_plot = c0 + c1 * x_plot

        # ── Figura e GridSpec ─────────────────────────────────────────────────
        # figsize=(9.61, 6.41) → 961×641 px
        fig = plt.figure(figsize=(9.61, 6.41), dpi=100)
        fig.patch.set_facecolor(DARK["bg"])

        gs = GridSpec(
            2, 1, figure=fig,
            height_ratios=[70, 30],
            hspace=0.08,
            left=0.09, right=0.97, top=0.88, bottom=0.10,
        )
        ax_bb  = fig.add_subplot(gs[0])
        ax_sec = fig.add_subplot(gs[1], sharex=ax_bb)

        self._aplicar_tema_dark(fig, [ax_bb, ax_sec])

        # ── Título e subtítulo ─────────────────────────────────────────────────
        fig.text(
            0.50, 0.955,
            f"Seção BB  —  Posição Ótima do Veículo  ·  Longarina {i}",
            ha="center", va="top",
            fontsize=11, fontweight="bold", color=DARK["accent"],
        )
        fig.text(
            0.50, 0.915,
            f"Q = {self.Q_kN} kN   |   q = {self.q_kNm} kN/m"
            f"   |   x_veh ótimo = {x_veh:.3f} m"
            + (f"   |   p' = {self.p_linha} kN/m" if self.p_linha > 0 else ""),
            ha="center", va="top",
            fontsize=8.5, color=DARK["fg"],
        )

        # ═════════════════════════════════════════════════════════════════════
        #  Painel superior: LI + veículo + áreas q2
        # ═════════════════════════════════════════════════════════════════════

        # Curva principal da LI
        ax_bb.plot(x_plot, y_plot,
                   color=DARK["li_line"], linewidth=2.4, zorder=4,
                   label=f"$\\eta_{{{i}}}(x)$")
        ax_bb.axhline(0, color=DARK["zero_line"], linewidth=1.0,
                      linestyle="-", zorder=2)

        # Envelope do veículo
        ax_bb.axvspan(x_veh, x_veh + veh_L, color=DARK["veh_fill"],
                      alpha=0.22, zorder=2,
                      label=f"Envelope  [{x_veh:.2f} m, {x_veh+veh_L:.2f} m]")
        ax_bb.axvline(x_veh,         color=DARK["veh_fill"], linewidth=1.2,
                      linestyle="--", alpha=0.88, zorder=5)
        ax_bb.axvline(x_veh + veh_L, color=DARK["veh_fill"], linewidth=1.2,
                      linestyle="--", alpha=0.88, zorder=5)

        # Cargas concentradas Q
        for idx, (pos_r, y_r, lbl_q) in enumerate(zip(
            VEH_POS_RODAS_M, [y1, y2],
            [f"Q₁ = {self.Q_kN}·{y1:.3f} = {self.Q_kN*y1:.3f} kN",
             f"Q₂ = {self.Q_kN}·{y2:.3f} = {self.Q_kN*y2:.3f} kN"]
        )):
            x_r = x_veh + pos_r
            ax_bb.plot([x_r, x_r], [0, y_r],
                       color=DARK["fill_Q"], linewidth=2.0,
                       linestyle="-.", alpha=0.90, zorder=5)
            ax_bb.plot(x_r, y_r, "o", color=DARK["fill_Q"],
                       markersize=10, zorder=6, label=lbl_q,
                       markeredgecolor="white", markeredgewidth=0.5)
            ax_bb.annotate(
                f"η = {y_r:.3f}",
                xy=(x_r, y_r), xytext=(0, 12),
                textcoords="offset points",
                ha="center", fontsize=8, color=DARK["fill_Q"],
                bbox=dict(boxstyle="round,pad=0.22", facecolor=DARK["bg"],
                          edgecolor=DARK["fill_Q"], linewidth=0.6, alpha=0.88),
                zorder=7,
            )

        # Área q2 (zona roulante fora do veículo, η > 0)
        mask_q2 = (
            (
                ((x_plot >= self._x_min_m) & (x_plot <= x_veh)) |
                ((x_plot >= x_veh + veh_L) & (x_plot <= self._x_max_m))
            ) & (y_plot > 0)
        )
        ax_bb.fill_between(x_plot, 0, y_plot, where=mask_q2,
                           color=DARK["fill_q2"], alpha=0.40, zorder=3,
                           label=f"Área q₂  (q = {self.q_kNm} kN/m)")

        # Passeios
        for j, (a, b) in enumerate(self._regioes_passeio):
            x_p  = np.linspace(a, b, 300)
            y_p  = c0 + c1 * x_p
            mask = y_p > 0
            if np.any(mask):
                ax_bb.fill_between(x_p, 0, y_p, where=mask,
                                   color=DARK["fill_passeio"], alpha=0.42, zorder=2,
                                   label=f"Passeio  p' = {self.p_linha} kN/m" if j == 0 else "")

        # Fronteiras NJ
        for x_nj in [self._x_min_m, self._x_max_m]:
            ax_bb.axvline(x_nj, color=DARK["nj_edge"], linewidth=1.0,
                          linestyle=":", alpha=0.82, zorder=6)

        # ── [AJUSTE] Anotação condicional ─────────────────────────────────────
        if exibir_anotacao:
            int_q2_val  = self._int_q2[k]
            tem_passeio = self.p_linha > 0.0 and len(self._regioes_passeio) > 0

            if tem_passeio:
                int_p = self._int_passeio_q2[k]
                q_p   = self.p_linha * int_p
                texto = (
                    f"Seção BB  —  Longarina {i}\n"
                    f"x_veh ótimo  =  {x_veh:.3f} m\n"
                    f"η(x_Q1) = {y1:.4f}    η(x_Q2) = {y2:.4f}\n"
                    f"η(x_Q1)+η(x_Q2) = {y1+y2:.4f}\n"
                    f"Q = {self.Q_kN} × {y1+y2:.4f} = {self._Q1[k]:.3f} kN\n"
                    f"∫η dx_q2  =  {int_q2_val:.5f} m   →   q·∫ = {self.q_kNm}×{int_q2_val:.5f} = {self.q_kNm*int_q2_val:.3f} kN/m\n"
                    f"∫η dx_p'  =  {int_p:.5f} m   →   p'·∫ = {self.p_linha}×{int_p:.5f} = {q_p:.3f} kN/m\n"
                    f"q2  =  {self.q_kNm*int_q2_val:.3f} + {q_p:.3f}  =  {self._q2[k]:.3f} kN/m"
                )
            else:
                texto = (
                    f"Seção BB  —  Longarina {i}\n"
                    f"x_veh ótimo  =  {x_veh:.3f} m\n"
                    f"η(x_Q1) = {y1:.4f}    η(x_Q2) = {y2:.4f}\n"
                    f"η(x_Q1)+η(x_Q2) = {y1+y2:.4f}\n"
                    f"Q = {self.Q_kN} × {y1+y2:.4f} = {self._Q1[k]:.3f} kN\n"
                    f"∫η dx_q2  =  {int_q2_val:.5f} m\n"
                    f"q2 = {self.q_kNm} × {int_q2_val:.5f} = {self._q2[k]:.3f} kN/m"
                )
            self._anotacao_resultado(ax_bb, texto, x=0.01, y=0.99)

        # Limites e rótulos
        ax_bb.set_xlim(-L2 * 1.05, L2 * 1.05)
        y_span = max(y_plot.max() - y_plot.min(), 0.1)
        ax_bb.set_ylim(y_plot.min() - 0.20 * y_span,
                       y_plot.max() + 0.20 * y_span)

        ax_bb.set_ylabel("η(x)", fontsize=10, color=DARK["fg"])
        ax_bb.tick_params(labelbottom=False)
        ax_bb.legend(
            facecolor=DARK["axes_bg"], edgecolor=DARK["spine"],
            labelcolor=DARK["fg"], fontsize=8.0, loc="upper right",
        )

        # ═════════════════════════════════════════════════════════════════════
        #  Painel inferior: Seção transversal com veículo posicionado
        # ═════════════════════════════════════════════════════════════════════
        self._desenhar_secao_transversal_mini(
            ax_sec, i_highlight=i, x_veh=x_veh, modo="bb"
        )

        # ── Dados para interatividade ─────────────────────────────────────────
        fig.interactive_data = {
            "ax":          ax_bb,
            "c0":          c0,
            "c1":          c1,
            "x_min":       float(-L2),
            "x_max":       float(L2),
            "x_roul_min":  self._x_min_m,
            "x_roul_max":  self._x_max_m,
            "longarina_i": i,
            "tipo":        "bb",
            "x_veh":       x_veh,
            "y1":          y1,
            "y2":          y2,
            "Q_kN":        self.Q_kN,
            "q2":          self._q2[k],
        }

        return fig

    # ──────────────────────────────────────────────────────────────────────────
    #  PLOT 4 — Todas as LIs (uma por longarina)
    # ──────────────────────────────────────────────────────────────────────────
    def plotar_todas_lis(self) -> List[plt.Figure]:
        """
        Retorna uma lista de matplotlib.figure.Figure, uma para cada longarina.
        Conveniente para exibição sequencial ou exportação.
        """
        return [self.plotar_li(i) for i in range(1, self.n + 1)]

    # ──────────────────────────────────────────────────────────────────────────
    #  PLOT 5 — Painel de resumo (LI + Seção AA + Seção BB para uma longarina)
    # ──────────────────────────────────────────────────────────────────────────
    def plotar_painel_longarina(self, i: int) -> plt.Figure:
        """
        Gera um painel com 3 subplots em coluna para a longarina i:
          [0] Linha de Influência  (η(x))
          [1] Seção AA             (área q1)
          [2] Seção BB             (veículo + áreas q2 e Q)

        Útil para exportação ou inserção em relatório técnico.

        Retorna
        -------
        matplotlib.figure.Figure
        """
        k   = i - 1
        c0  = self._coef_lin[k]
        c1  = self._coef_ang[k]
        L2  = self.L_total_m / 2.0

        x_plot = np.linspace(-L2, L2, 1200)
        y_plot = c0 + c1 * x_plot

        fig = plt.figure(figsize=(14, 14))
        fig.patch.set_facecolor(DARK["bg"])
        gs = GridSpec(3, 1, figure=fig, hspace=0.42)
        axes = [fig.add_subplot(gs[r]) for r in range(3)]
        self._aplicar_tema_dark(fig, axes)

        titulos = [
            f"[LI]   Linha de Influência — Longarina {i}",
            f"[AA]   Carga Distribuída q₁ — Longarina {i}",
            f"[BB]   Posição Ótima do Veículo — Longarina {i}",
        ]

        veh_L = VEH_COMPRIMENTO_M
        x_veh = self._x_crit[k]
        y1, y2 = self._y_Q[k]
        int_q1  = self._int_q1[k]
        int_q2  = self._int_q2[k]
        tem_passeio = self.p_linha > 0.0 and len(self._regioes_passeio) > 0

        for ax_idx, ax in enumerate(axes):
            ax.plot(x_plot, y_plot, color=DARK["li_line"], linewidth=2.2, zorder=3,
                    label=f"η{i}(x)  –  {self._formatar_equacao(k)}")
            ax.axhline(0, color=DARK["zero_line"], linewidth=1.0, linestyle="-")

            for x_nj in [self._x_min_m, self._x_max_m]:
                ax.axvline(x_nj, color=DARK["nj_edge"], linewidth=0.9,
                           linestyle=":", alpha=0.70)

            # ── Subplot 0: LI pura ────────────────────────────────────────
            if ax_idx == 0:
                ax.axvspan(self._x_min_m, self._x_max_m,
                           color=DARK["li_line"], alpha=0.05)
                for j, (a, b) in enumerate(self._regioes_passeio):
                    ax.axvspan(a, b, color=DARK["fill_passeio"], alpha=0.08)
                for k2, xi2 in enumerate(self._xi_m):
                    y_e = c0 + c1 * xi2
                    ax.plot(xi2, y_e, "o", color=DARK["accent"], markersize=6, zorder=5)
                    ax.annotate(f"L{k2+1} ({xi2:.2f}m)\nη={y_e:.3f}",
                                xy=(xi2, y_e), xytext=(0, 14 if y_e >= 0 else -26),
                                textcoords="offset points",
                                ha="center", fontsize=7, color=DARK["accent"])

            # ── Subplot 1: Seção AA ───────────────────────────────────────
            elif ax_idx == 1:
                mask_q = ((x_plot >= self._x_min_m) & (x_plot <= self._x_max_m)
                          & (y_plot > 0))
                ax.fill_between(x_plot, 0, y_plot, where=mask_q,
                                color=DARK["fill_q1"], alpha=0.40, zorder=2,
                                label=f"Área q1  (q={self.q_kNm} kN/m)")
                for j, (a, b) in enumerate(self._regioes_passeio):
                    x_p = np.linspace(a, b, 300)
                    y_p = c0 + c1 * x_p
                    ax.fill_between(x_p, 0, y_p, where=y_p > 0,
                                    color=DARK["fill_passeio"], alpha=0.42, zorder=2,
                                    label="Passeio" if j == 0 else "")
                # ── [AJUSTE] Texto do painel com parcela p' ───────────────
                if tem_passeio:
                    int_p = self._int_passeio_q1[k]
                    q_p   = self.p_linha * int_p
                    txt_aa = (
                        f"∫η_q1={int_q1:.5f}m  q·∫={self.q_kNm*int_q1:.3f} kN/m\n"
                        f"∫η_p'={int_p:.5f}m  p'·∫={q_p:.3f} kN/m\n"
                        f"q1 = {self._q1[k]:.3f} kN/m"
                    )
                else:
                    txt_aa = f"∫η dx = {int_q1:.5f} m   →   q1 = {self._q1[k]:.3f} kN/m"
                ax.text(0.01, 0.97, txt_aa,
                        transform=ax.transAxes, ha="left", va="top",
                        fontsize=8, color=DARK["fg"], family="monospace",
                        bbox=dict(fc=DARK["axes_bg"], ec=DARK["spine"], alpha=0.85, pad=4))

            # ── Subplot 2: Seção BB ───────────────────────────────────────
            else:
                ax.axvspan(x_veh, x_veh + veh_L, color=DARK["veh_fill"],
                           alpha=0.20, zorder=2, label="Envelope veículo")
                ax.axvline(x_veh,         color=DARK["veh_fill"], linewidth=1.1,
                           linestyle="--", alpha=0.85)
                ax.axvline(x_veh + veh_L, color=DARK["veh_fill"], linewidth=1.1,
                           linestyle="--", alpha=0.85)

                for pos_r, y_r, lbl_idx in zip(VEH_POS_RODAS_M, [y1, y2], [1, 2]):
                    x_r = x_veh + pos_r
                    ax.plot([x_r, x_r], [0, y_r], color=DARK["fill_Q"],
                            linewidth=1.8, linestyle="-.", alpha=0.9, zorder=4)
                    ax.plot(x_r, y_r, "o", color=DARK["fill_Q"], markersize=9, zorder=5,
                            label=f"Q{lbl_idx}: {self.Q_kN}·{y_r:.3f}={self.Q_kN*y_r:.3f}kN")
                    ax.annotate(f"η={y_r:.3f}", xy=(x_r, y_r), xytext=(0, 10),
                                textcoords="offset points", ha="center",
                                fontsize=7.5, color=DARK["fill_Q"])

                mask_q2 = (
                    (((x_plot >= self._x_min_m) & (x_plot <= x_veh)) |
                     ((x_plot >= x_veh + veh_L) & (x_plot <= self._x_max_m)))
                    & (y_plot > 0)
                )
                ax.fill_between(x_plot, 0, y_plot, where=mask_q2,
                                color=DARK["fill_q2"], alpha=0.40, zorder=2,
                                label=f"Área q2  (q={self.q_kNm} kN/m)")
                for j, (a, b) in enumerate(self._regioes_passeio):
                    x_p = np.linspace(a, b, 300)
                    y_p = c0 + c1 * x_p
                    ax.fill_between(x_p, 0, y_p, where=y_p > 0,
                                    color=DARK["fill_passeio"], alpha=0.42, zorder=2,
                                    label="Passeio" if j == 0 else "")
                # ── [AJUSTE] Texto do painel com parcela p' ───────────────
                if tem_passeio:
                    int_p = self._int_passeio_q2[k]
                    q_p   = self.p_linha * int_p
                    txt_bb = (
                        f"x_veh={x_veh:.3f}m  ∫η_q2={int_q2:.5f}m  q·∫={self.q_kNm*int_q2:.3f} kN/m\n"
                        f"∫η_p'={int_p:.5f}m  p'·∫={q_p:.3f} kN/m\n"
                        f"η_Q1+η_Q2={y1:.3f}+{y2:.3f}={y1+y2:.3f}\n"
                        f"q2 = {self._q2[k]:.3f} kN/m    Q = {self._Q1[k]:.3f} kN"
                    )
                else:
                    txt_bb = (
                        f"x_veh={x_veh:.3f}m  |  ∫η_q2={int_q2:.5f}m  |  "
                        f"η_Q1+η_Q2={y1:.3f}+{y2:.3f}={y1+y2:.3f}\n"
                        f"q2 = {self._q2[k]:.3f} kN/m    Q = {self._Q1[k]:.3f} kN"
                    )
                ax.text(0.01, 0.99, txt_bb,
                        transform=ax.transAxes, ha="left", va="top",
                        fontsize=8, color=DARK["fg"], family="monospace",
                        bbox=dict(fc=DARK["axes_bg"], ec=DARK["spine"], alpha=0.85, pad=4))

            ax.set_title(titulos[ax_idx], fontsize=10, fontweight="bold",
                         color=DARK["fg"], pad=6)
            ax.set_xlabel("x [m]", fontsize=9, color=DARK["fg"])
            ax.set_ylabel("η(x)",  fontsize=9, color=DARK["fg"])
            ax.legend(facecolor=DARK["axes_bg"], edgecolor=DARK["spine"],
                      labelcolor=DARK["fg"], fontsize=7.5, loc="upper right")
            ax.set_xlim(-L2 * 1.05, L2 * 1.05)

        fig.suptitle(
            f"Trem-Tipo Longitudinal — Método de Courbon | "
            f"Q={self.Q_kN} kN  q={self.q_kNm} kN/m  "
            f"n={self.n}  Σxi²={self._sum_xi2:.3f} m²",
            fontsize=11, fontweight="bold", color=DARK["accent"],
            y=0.995
        )
        return fig

    # ════════════════════════════════════════════════════════════════════════════════
    # 1. MÉTODO: obter_relatorio_lis() — Memorial das Linhas de Influência
    # ════════════════════════════════════════════════════════════════════════════════

    def obter_relatorio_lis(self) -> Tuple[str, str]:
        """
        Memorial de cálculo detalhado para a determinação das Linhas de Influência (LI)
        dos coeficientes de distribuição transversal pelo Método de Engesser-Courbon.

        Conteúdo:
            • Geometria da seção transversal e posicionamento das longarinas.
            • Cálculo do centro elástico e coordenadas relativas xi.
            • Dedução da fórmula de Courbon: η_ij(x) = 1/n + (xi·x)/Σxi².
            • Tabela com xi, xi², Σxi².
            • Equações completas das LIs para cada longarina.
            • Interpretação física e gráfica (não inclui plotagem, apenas descrição).

        Retorna:
            Tuple[str, str]: (texto_plano, html_formatado)
        """
        # Coleta de dados
        n = self.n
        L_total = self.L_total_m
        d_ext = self.d_ext_m
        d_eixos = self.d_eixos_m
        xi_list = self._xi_m
        sum_xi2 = self._sum_xi2

        # ─────────────────────────────────────────────────────────────────────
        # TEXTO PLANO
        # ─────────────────────────────────────────────────────────────────────
        SEP_D = "=" * 80
        SEP_S = "-" * 80
        SEP_M = "-" * 60

        txt = []
        txt.append(SEP_D)
        txt.append("MEMORIAL DE CÁLCULO – LINHAS DE INFLUÊNCIA DE COURBON")
        txt.append("Coeficientes de Distribuição Transversal para Longarinas")
        txt.append("Método de Engesser-Courbon – Seção Transversal Rígida")
        txt.append(SEP_D)

        # SEÇÃO 1 – DADOS GEOMÉTRICOS
        txt.append("")
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 1 – GEOMETRIA DA SUPERESTRUTURA                     │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append(f"  Número de longarinas (n)                : {n}")
        txt.append(f"  Largura total do tabuleiro (L_total)    : {L_total:.3f} m")
        txt.append(f"  Distância da borda à 1ª longarina (d_ext): {d_ext:.3f} m")
        if n > 1:
            txt.append(f"  Espaçamento entre eixos (d_eixos)       : {d_eixos:.3f} m")
        else:
            txt.append("  Espaçamento entre eixos                 : N/A (apenas 1 longarina)")
        txt.append("")

        # SEÇÃO 2 – CENTRO ELÁSTICO E COORDENADAS RELATIVAS
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 2 – CENTRO ELÁSTICO E COORDENADAS RELATIVAS xi     │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Hipótese de Courbon: a seção transversal comporta-se como")
        txt.append("  um corpo rígido apoiado sobre molas elásticas de igual rigidez.")
        txt.append("  O centro elástico (x0) coincide com o centro geométrico:")
        txt.append(f"      x0 = L_total / 2 = {L_total:.3f} / 2 = {L_total/2:.3f} m")
        txt.append("")
        txt.append("  Posição absoluta de cada longarina i (medida da borda esquerda):")
        txt.append("      xi_abs = d_ext + (i - 1) · d_eixos")
        txt.append("")
        txt.append("  Coordenada relativa xi (positiva para a direita de x0):")
        txt.append("      xi = xi_abs - x0")
        txt.append("")
        txt.append("  Tabela de coordenadas:")
        txt.append(f"  {'i':>4}  {'xi_abs [m]':>12}  {'xi [m]':>12}  {'xi² [m²]':>12}")
        txt.append("  " + "-" * 46)
        for i in range(1, n+1):
            xi_abs = d_ext + (i-1)*d_eixos
            xi_val = xi_list[i-1]
            xi2_val = xi_val**2
            txt.append(f"  {i:>4}  {xi_abs:>12.4f}  {xi_val:>12.4f}  {xi2_val:>12.6f}")
        txt.append("  " + "-" * 46)
        txt.append(f"  Σ xi² = {sum_xi2:.6f} m²")
        txt.append("")

        # SEÇÃO 3 – DEDUÇÃO DA FÓRMULA DE COURBON
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 3 – COEFICIENTE DE DISTRIBUIÇÃO TRANSVERSAL η_ij   │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Para uma carga unitária aplicada na posição transversal xj,")
        txt.append("  a reação na longarina i é dada pelo coeficiente η_ij(xj):")
        txt.append("")
        txt.append("              1       xi · xj")
        txt.append("    η_ij(xj) = ───  +  ────────")
        txt.append("              n        Σ xi²")
        txt.append("")
        txt.append("  onde:")
        txt.append("    n      = número de longarinas")
        txt.append("    xi     = coordenada da longarina i (relativa a x0)")
        txt.append("    Σ xi²  = soma dos quadrados das coordenadas")
        txt.append("")
        txt.append("  Substituindo os valores numéricos:")
        txt.append(f"    n = {n}")
        txt.append(f"    Σ xi² = {sum_xi2:.6f} m²")
        txt.append("")
        txt.append("  As equações das Linhas de Influência (η_i em função de x) são:")
        txt.append("")
        txt.append(f"  {'i':>4}  {'Equação η_i(x)':<45}")
        txt.append("  " + "-" * 52)
        for i in range(1, n+1):
            eq = self._formatar_equacao(i-1)
            txt.append(f"  {i:>4}  {eq}")
        txt.append("")
        txt.append("  Observação: para longarinas com xi = 0 (sobre o centro elástico),")
        txt.append("  η é constante e igual a 1/n (distribuição uniforme).")
        txt.append("")

        # SEÇÃO 4 – INTERPRETAÇÃO GRÁFICA
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 4 – INTERPRETAÇÃO GRÁFICA DAS LINHAS DE INFLUÊNCIA│")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  As LIs são retas com coeficiente angular c1 = xi / Σxi².")
        txt.append("  • Se xi > 0 (longarina à direita): reta crescente.")
        txt.append("  • Se xi < 0 (longarina à esquerda): reta decrescente.")
        txt.append("")
        txt.append("  A ordenada η representa a fração da carga unitária absorvida")
        txt.append("  pela longarina i quando a carga está na posição x.")
        txt.append("  Valores negativos de η indicam alívio (levantamento), mas são")
        txt.append("  desprezados nos carregamentos (considera-se apenas η > 0).")
        txt.append("")
        txt.append(SEP_D)
        txt.append("FIM DO MEMORIAL – LINHAS DE INFLUÊNCIA")
        txt.append(SEP_D)

        texto_plano = "\n".join(txt)

        # ─────────────────────────────────────────────────────────────────────
        # HTML (TEMA ESCURO)
        # ─────────────────────────────────────────────────────────────────────
        rows_coord = ""
        for i in range(1, n+1):
            xi_abs = d_ext + (i-1)*d_eixos
            xi_val = xi_list[i-1]
            xi2_val = xi_val**2
            rows_coord += f"<tr><td>{i}</td><td>{xi_abs:.4f}</td><td>{xi_val:.4f}</td><td>{xi2_val:.6f}</td></tr>"

        rows_eq = ""
        for i in range(1, n+1):
            eq = self._formatar_equacao(i-1)
            rows_eq += f"<tr><td>{i}</td><td style='text-align:left;'><code>{eq}</code></td></tr>"

        # ─── Dados complementares para o HTML ────────────────────────────────
        rows_li_detail = ""
        for i in range(1, n+1):
            k = i - 1
            xi_val = xi_list[k]
            c1_val = xi_val / sum_xi2 if abs(sum_xi2) > 1e-15 else 0.0
            x_zero_val = -(1.0/n) / c1_val if abs(c1_val) > 1e-15 else float('inf')
            direcao = "crescente (→ direita)" if c1_val > 0 else ("decrescente (→ esquerda)" if c1_val < 0 else "constante (xi=0)")
            x_zero_str = f"{x_zero_val:.4f} m" if abs(x_zero_val) < 1e6 else "∞ (constante)"
            eq = self._formatar_equacao(k)
            rows_li_detail += (
                f"<tr><td><strong>L{i}</strong></td>"
                f"<td><code>{eq}</code></td>"
                f"<td>{c1_val:+.6f}</td>"
                f"<td>{x_zero_str}</td>"
                f"<td>{direcao}</td></tr>"
            )

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memorial – Linhas de Influência de Courbon</title>
<style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: 'Segoe UI', Tahoma, Geneva, sans-serif;
        background: #0a0f1e;
        color: #dde6f5;
        padding: 24px;
        font-size: 14px;
        line-height: 1.75;
    }}
    .container {{
        max-width: 1100px;
        margin: 0 auto;
        background: #111827;
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 12px 48px rgba(0,0,0,0.7);
        border: 1px solid #1e3a5f;
    }}
    /* ── Cabeçalho ── */
    .header {{
        background: linear-gradient(135deg, #0d1b4b 0%, #1a3272 40%, #0e2257 100%);
        padding: 36px 40px;
        text-align: center;
        border-bottom: 2px solid #2563eb;
        position: relative;
    }}
    .header::after {{
        content: '';
        position: absolute;
        bottom: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, transparent, #60a5fa, #a78bfa, #60a5fa, transparent);
    }}
    .header h1 {{ font-size: 1.65em; font-weight: 700; letter-spacing: 0.4px; color: #e2effe; margin-bottom: 6px; }}
    .header .subtitle {{ font-size: 0.95em; color: #93c5fd; margin-bottom: 4px; }}
    .header .norma {{ font-size: 0.82em; color: #64748b; letter-spacing: 0.5px; }}
    /* ── Índice / breadcrumb ── */
    .toc {{
        background: #0f172a;
        padding: 14px 40px;
        border-bottom: 1px solid #1e293b;
        font-size: 0.82em;
        color: #64748b;
    }}
    .toc a {{ color: #60a5fa; text-decoration: none; margin: 0 6px; }}
    .toc a:hover {{ text-decoration: underline; }}
    /* ── Conteúdo ── */
    .content {{ padding: 36px 40px; }}
    /* ── Seções ── */
    .section {{
        margin-bottom: 36px;
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #1e3a5f;
    }}
    .section-header {{
        background: linear-gradient(90deg, #1e3a5f, #172040);
        padding: 14px 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .section-number {{
        background: #2563eb;
        color: white;
        font-size: 0.78em;
        font-weight: 700;
        padding: 3px 9px;
        border-radius: 20px;
        white-space: nowrap;
    }}
    .section-title {{
        font-size: 1.05em;
        font-weight: 700;
        color: #93c5fd;
        letter-spacing: 0.2px;
    }}
    .section-body {{
        padding: 20px 24px;
        background: rgba(17,24,39,0.6);
    }}
    /* ── Texto e parágrafos ── */
    .section-body p {{ margin-bottom: 10px; color: #cbd5e1; }}
    .section-body p:last-child {{ margin-bottom: 0; }}
    .section-body ul {{ margin: 8px 0 8px 22px; color: #cbd5e1; }}
    .section-body li {{ margin-bottom: 4px; }}
    /* ── Destaque de fórmula ── */
    .formula-block {{
        background: #0a0f1e;
        border-left: 4px solid #f59e0b;
        border-radius: 0 8px 8px 0;
        padding: 14px 20px;
        margin: 14px 0;
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.95em;
        color: #fef3c7;
        white-space: pre-wrap;
        line-height: 1.9;
    }}
    .formula-inline {{
        font-family: 'Courier New', monospace;
        background: #1e293b;
        padding: 2px 8px;
        border-radius: 4px;
        color: #fbbf24;
        font-size: 0.93em;
    }}
    /* ── Caixa de resultado ── */
    .result-box {{
        background: #0c1a30;
        border: 1px solid #2563eb;
        border-radius: 8px;
        padding: 14px 18px;
        margin: 14px 0;
        color: #93c5fd;
        font-size: 1.0em;
    }}
    .result-box strong {{ color: #60a5fa; }}
    /* ── Info badge ── */
    .info-badge {{
        display: inline-block;
        background: #1e3a5f;
        border: 1px solid #3b82f6;
        color: #93c5fd;
        font-size: 0.80em;
        padding: 3px 10px;
        border-radius: 12px;
        margin: 2px 2px;
    }}
    /* ── Tabelas ── */
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.86em; }}
    thead th {{
        background: #1e3a5f;
        color: #93c5fd;
        padding: 9px 12px;
        text-align: center;
        border-bottom: 2px solid #2563eb;
        font-weight: 700;
        letter-spacing: 0.2px;
        white-space: nowrap;
    }}
    tbody td {{
        padding: 7px 12px;
        border-bottom: 1px solid #1e293b;
        text-align: center;
        color: #cbd5e1;
    }}
    tbody tr:hover td {{ background: rgba(59,130,246,0.07); }}
    tbody td:first-child {{ text-align: center; font-weight: 700; color: #60a5fa; }}
    /* ── Tabela de parâmetros (2 colunas) ── */
    .param-table td {{ text-align: left !important; }}
    .param-table td:first-child {{ color: #94a3b8 !important; font-weight: normal !important; width: 55%; }}
    .param-table td:last-child {{ color: #e2e8f0; font-weight: 600; text-align: right !important; }}
    /* ── Nota de rodapé da seção ── */
    .section-note {{
        background: rgba(251,191,36,0.08);
        border-left: 3px solid #f59e0b;
        border-radius: 0 6px 6px 0;
        padding: 10px 14px;
        margin-top: 14px;
        font-size: 0.88em;
        color: #fde68a;
    }}
    /* ── Footer ── */
    .footer {{
        background: #0a0f1e;
        padding: 18px 40px;
        border-top: 1px solid #1e293b;
        text-align: center;
        color: #475569;
        font-size: 0.80em;
        line-height: 1.6;
    }}
    code {{ background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #fbbf24; font-family: 'Courier New', monospace; font-size: 0.91em; }}
</style>
</head>
<body>
<div class="container">

  <!-- ══ Cabeçalho ══════════════════════════════════════════════════════ -->
  <div class="header">
    <h1>📐 Memorial de Cálculo — Linhas de Influência de Courbon</h1>
    <p class="subtitle">Coeficientes de Distribuição Transversal · Método de Engesser-Courbon</p>
    <p class="norma">NBR 7188:2013 · Cargas Móveis em Pontes Rodoviárias · Revisão calculada automaticamente</p>
  </div>

  <!-- ══ Índice ══════════════════════════════════════════════════════════ -->
  <div class="toc">
    ▸ Seções:
    <a href="#s1">1 – Geometria</a> ·
    <a href="#s2">2 – Hipóteses do Método</a> ·
    <a href="#s3">3 – Centro Elástico</a> ·
    <a href="#s4">4 – Fórmula de Courbon</a> ·
    <a href="#s5">5 – Equações das LIs</a> ·
    <a href="#s6">6 – Interpretação</a>
  </div>

  <div class="content">

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s1">
      <div class="section-header">
        <span class="section-number">SEÇÃO 1</span>
        <span class="section-title">📌 Geometria da Superestrutura</span>
      </div>
      <div class="section-body">
        <p>
          Os dados geométricos abaixo definem o posicionamento transversal das longarinas
          em relação à largura total do tabuleiro. O espaçamento entre eixos é calculado
          a partir da largura útil entre as longarinas extremas, dividida pelo número de
          vãos transversais (n − 1).
        </p>
        <table class="param-table">
          <tbody>
            <tr><td>Número de longarinas (n)</td><td>{n}</td></tr>
            <tr><td>Largura total do tabuleiro (L<sub>total</sub>)</td><td>{L_total:.4f} m</td></tr>
            <tr><td>Distância da borda esquerda à eixo da Longarina 1 (d<sub>ext</sub>)</td><td>{d_ext:.4f} m</td></tr>
            <tr><td>Espaçamento entre eixos de longarinas consecutivas (d<sub>eixos</sub>)</td><td>{d_eixos:.4f} m{'  ← calculado: (L − 2·d_ext)/(n−1)' if n > 1 else '  (única longarina)'}</td></tr>
          </tbody>
        </table>
        <div class="section-note">
          ⚠️ O Método de Engesser-Courbon admite que todas as longarinas possuem
          rigidez à flexão <strong>EI</strong> igual. Caso haja variação significativa de EI entre longarinas,
          os coeficientes de distribuição devem ser ponderados pela rigidez relativa (η ponderado).
        </div>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s2">
      <div class="section-header">
        <span class="section-number">SEÇÃO 2</span>
        <span class="section-title">📖 Hipóteses Fundamentais do Método de Engesser-Courbon</span>
      </div>
      <div class="section-body">
        <p>
          O Método de Engesser-Courbon, amplamente utilizado na análise de pontes com grelha
          transversal, baseia-se nas seguintes hipóteses simplificadoras:
        </p>
        <ul>
          <li><strong>Seção transversal indeformável:</strong> a laje de concreto e as transversinas
              garantem rigidez suficiente para que a seção transversal se comporte como um corpo
              rígido em rotação e translação vertical.</li>
          <li><strong>Apoios elásticos equivalentes:</strong> cada longarina é idealizada como
              uma mola elástica de rigidez proporcional ao seu EI. Com EI iguais, as rigidezes
              são idênticas e o ponto de aplicação da resultante vertical determina a rotação.</li>
          <li><strong>Equilíbrio de translação e rotação:</strong> a condição de equilíbrio vertical
              (soma das reações = carga aplicada) e equilíbrio de momentos em torno do centro
              elástico conduzem diretamente à fórmula do coeficiente η.</li>
          <li><strong>Validade:</strong> o método é adequado para pontes com relação
              comprimento/largura (L/B) entre 2 e 5. Para pontes muito largas ou muito curtas,
              métodos mais refinados (elementos finitos, analogia de grelha) são recomendados.</li>
        </ul>
        <div class="result-box">
          <strong>Referências normativas:</strong><br>
          • NBR 7188:2013 — Carga Móvel Rodoviária e de Pedestre em Pontes, Viadutos, Passarelas e Obras Similares<br>
          • NBR 6118:2014 — Projeto de Estruturas de Concreto<br>
          • Pfeil, W. — "Pontes em Concreto Armado", 3ª ed.
        </div>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s3">
      <div class="section-header">
        <span class="section-number">SEÇÃO 3</span>
        <span class="section-title">📍 Centro Elástico e Coordenadas Relativas x<sub>i</sub></span>
      </div>
      <div class="section-body">
        <p>
          O <strong>centro elástico</strong> (x₀) é o ponto de referência em relação ao qual
          as coordenadas transversais das longarinas são medidas. Para longarinas com EI iguais
          e igualmente espaçadas, coincide com o centroide geométrico da seção:
        </p>
        <div class="formula-block">x₀ = L_total / 2 = {L_total:.4f} / 2 = {L_total/2:.4f} m</div>
        <p>
          A coordenada absoluta de cada longarina <em>i</em> (medida a partir da borda esquerda do
          tabuleiro) e sua coordenada relativa em relação ao centro elástico são:
        </p>
        <div class="formula-block">xi_abs(i) = d_ext + (i − 1) · d_eixos
xi(i)     = xi_abs(i) − x₀   [m, positivo para a direita de x₀]</div>
        <table>
          <thead>
            <tr>
              <th>i</th>
              <th>xi_abs [m]</th>
              <th>xi [m]</th>
              <th>xi² [m²]</th>
            </tr>
          </thead>
          <tbody>{rows_coord}</tbody>
        </table>
        <div class="result-box">
          <strong>Σ xi² = {sum_xi2:.6f} m²</strong>
          &nbsp;—&nbsp; Este valor é o <em>momento de inércia polar</em> das rigidezes em relação
          ao centro elástico. Quanto maior Σxi², menor é o coeficiente angular das LIs e
          mais uniforme é a distribuição transversal.
        </div>
        <div class="section-note">
          📌 Convenção de sinais: xi &gt; 0 → longarina à <strong>direita</strong> do centro elástico;
          xi &lt; 0 → longarina à <strong>esquerda</strong>. Longarinas com xi = 0 absorvem apenas
          a parcela de translação (1/n), sem componente de rotação.
        </div>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s4">
      <div class="section-header">
        <span class="section-number">SEÇÃO 4</span>
        <span class="section-title">📐 Dedução do Coeficiente de Distribuição η<sub>ij</sub></span>
      </div>
      <div class="section-body">
        <p>
          Considere uma carga unitária aplicada na posição transversal <em>xj</em> sobre a laje.
          A seção transversal rígida experimenta uma translação vertical <em>δ</em> e uma rotação
          <em>θ</em> em torno do centro elástico. A reação na longarina <em>i</em> (no ponto xi)
          resulta da superposição dessas duas componentes:
        </p>
        <div class="formula-block">Componente de translação (equilíbrio vertical):
    Σ Ri = 1  →  n · δ · k = 1  →  δ = 1/(n·k)  →  R_translação = k · δ = 1/n

Componente de rotação (equilíbrio de momentos em x₀):
    Σ (Ri · xi) = 1 · xj  →  θ · k · Σxi² = xj  →  θ = xj / (k · Σxi²)
    R_rotação_i = k · θ · xi = (xi · xj) / Σxi²

Coeficiente de distribuição transversal η_ij:
                    1       xi · xj
    η_ij(xj) = ───  +  ──────────
                    n        Σ xi²

    Reescrito como LI linear em xj:
    η_i(xj) = c₀ + c₁ · xj
    onde:
        c₀ = 1/n              (termo constante — parcela de translação)
        c₁ = xi / Σxi²        (coef. angular — parcela de rotação)</div>
        <p>
          A fórmula satisfaz automaticamente a condição de equilíbrio global:
          a soma de η_ij para todas as longarinas, para qualquer posição xj, é sempre igual a 1.
        </p>
        <p>
          Com os valores calculados neste projeto:
        </p>
        <div class="formula-block">n = {n}     →   c₀ = 1/{n} = {1.0/n:.6f}
Σ xi² = {sum_xi2:.6f} m²
c₁(i) = xi / {sum_xi2:.4f}   [varia por longarina, vide Seção 5]</div>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s5">
      <div class="section-header">
        <span class="section-number">SEÇÃO 5</span>
        <span class="section-title">📈 Equações das Linhas de Influência por Longarina</span>
      </div>
      <div class="section-body">
        <p>
          Substituindo os valores de xi e Σxi² na fórmula de Courbon, obtêm-se as equações
          das Linhas de Influência (LI) para cada longarina. A LI representa a fração da carga
          unitária absorvida pela longarina <em>i</em> quando a carga está na posição transversal <em>x</em>.
        </p>
        <table>
          <thead>
            <tr>
              <th>Longarina</th>
              <th>Equação η(x)</th>
              <th>c₁ [m⁻¹]</th>
              <th>Zero da LI (x_zero)</th>
              <th>Comportamento</th>
            </tr>
          </thead>
          <tbody>{rows_li_detail}</tbody>
        </table>
        <div class="section-note">
          📌 Verificação: a soma de η para todas as longarinas em qualquer posição x deve ser
          exatamente 1.0 (partição da unidade). Isto decorre da condição de equilíbrio vertical
          da seção rígida.
        </div>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s6">
      <div class="section-header">
        <span class="section-number">SEÇÃO 6</span>
        <span class="section-title">📊 Interpretação Física e Aplicação no Cálculo de Esforços</span>
      </div>
      <div class="section-body">
        <p>
          As Linhas de Influência obtidas pelo Método de Courbon são utilizadas para determinar
          a <strong>carga equivalente por longarina</strong> (trem-tipo longitudinal), que considera
          a posição transversal mais desfavorável do veículo-tipo e da carga distribuída.
        </p>
        <ul>
          <li><strong>Zona rolável:</strong> faixa entre as faces internas das barreiras New Jersey.
              Veículos e cargas distribuídas só podem ser posicionados nesta zona.</li>
          <li><strong>Seção AA (momento máximo):</strong> toda a zona rolável com η &gt; 0 é carregada
              pela carga distribuída q, integrando a LI analiticamente sobre essa região.</li>
          <li><strong>Seção BB (cortante máximo no apoio):</strong> o veículo-tipo é varrido
              transversalmente para encontrar a posição que maximiza q₂ + Q, onde Q é a carga
              concentrada ponderada pela LI nas posições das rodas.</li>
          <li><strong>Região negativa:</strong> quando η(x) &lt; 0, indica <em>alívio</em> (força
              de levantamento) na longarina. Por segurança estrutural, a parcela negativa não é
              somada ao carregamento — aplica-se apenas η &gt; 0.</li>
        </ul>
        <div class="result-box">
          <strong>Critério de carregamento (NBR 7188:2013):</strong><br>
          Para a seção AA, integra-se η(x) somente onde η &gt; 0 e dentro da zona rolável.<br>
          Para a seção BB, além da integração de η &gt; 0 na zona rolável fora do veículo,
          somam-se as ordenadas η nas posições das rodas (multiplicadas por Q),
          sem restrição de sinal — a posição ótima é aquela que maximiza a soma total.
        </div>
        <div class="section-note">
          🔁 Simetria: para estruturas simétricas (longarinas equidistantes do centro elástico),
          as LIs de longarinas opostas são simétricas em relação ao eixo x = 0. Por consequência,
          os carregamentos equivalentes (q1, q2, Q) de longarinas simétricas são iguais em módulo.
          Este é um critério eficaz de verificação dos resultados.
        </div>
      </div>
    </div>

  </div><!-- /content -->

  <div class="footer">
    Memorial de Cálculo – Linhas de Influência de Courbon
    &nbsp;·&nbsp; Método de Engesser-Courbon
    &nbsp;·&nbsp; NBR 7188:2013
    &nbsp;·&nbsp; Gerado automaticamente pelo módulo <code>Calculadora_Trem_Tipo_Longarina</code>
  </div>

</div><!-- /container -->
</body>
</html>"""

        return texto_plano, html


    # ════════════════════════════════════════════════════════════════════════════════
    # 2. MÉTODO: obter_relatorio_trem_tipo() — Memorial do Trem-Tipo Longitudinal
    # ════════════════════════════════════════════════════════════════════════════════

    def obter_relatorio_trem_tipo(self) -> Tuple[str, str]:
        """
        Memorial de cálculo completo para a determinação do trem-tipo longitudinal
        equivalente (q1, q2, Q) para cada longarina, utilizando as Linhas de Influência
        de Courbon.

        Conteúdo:
            • Definição das zonas de carregamento (rolável e passeios).
            • Seção AA: integração analítica para carga distribuída q1.
            • Seção BB: varredura numérica para posição ótima do veículo e cálculo de q2 e Q.
            • Tabelas detalhadas com integrais e cargas por longarina.
            • Identificação da longarina crítica (maior soma q1+q2+Q).
            • Tabela resumo final.

        Retorna:
            Tuple[str, str]: (texto_plano, html_formatado)
        """
        # Coleta de dados
        n = self.n
        Q = self.Q_kN
        q = self.q_kNm
        p_linha = self.p_linha
        L_total = self.L_total_m
        classe = self.st.classe
        config_classe = self.MAPA_CLASSES.get(classe, {})
        tem_passeio = len(self._regioes_passeio) > 0 and p_linha > 0

        x_min = self._x_min_m
        x_max = self._x_max_m
        regioes_passeio = self._regioes_passeio

        q1_vals = self._q1
        q2_vals = self._q2
        Q1_vals = self._Q1
        int_q1 = self._int_q1
        int_q2 = self._int_q2
        y_Q_vals = self._y_Q
        x_crit = self._x_crit

        crit = self.get_configuracao_critica()

        # ─────────────────────────────────────────────────────────────────────
        # TEXTO PLANO
        # ─────────────────────────────────────────────────────────────────────
        SEP_D = "=" * 80
        SEP_S = "-" * 80
        SEP_M = "-" * 60

        txt = []
        txt.append(SEP_D)
        txt.append("MEMORIAL DE CÁLCULO – TREM-TIPO LONGITUDINAL EQUIVALENTE")
        txt.append("Cargas Distribuídas e Concentradas por Longarina (Courbon)")
        txt.append("NBR 7188:2013 – Cargas Móveis em Pontes Rodoviárias")
        txt.append(SEP_D)

        # SEÇÃO 1 – DADOS DO CARREGAMENTO
        txt.append("")
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 1 – CARREGAMENTO MÓVEL (TREM-TIPO)                 │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append(f"  Classe da via (NBR 7188)        : {classe}")
        txt.append(f"  Carga concentrada por roda (Q)   : {Q:.2f} kN")
        txt.append(f"  Carga distribuída na pista (q)   : {q:.3f} kN/m²")
        if tem_passeio:
            txt.append(f"  Carga distribuída no passeio (p'): {p_linha:.3f} kN/m²")
        else:
            txt.append("  Carga no passeio (p')            : 0.0 kN/m² (sem passeio)")
        txt.append("")
        txt.append("  Veículo-tipo padrão:")
        txt.append(f"    • Envelope transversal         : {VEH_COMPRIMENTO_M:.2f} m")
        txt.append(f"    • Posição das rodas (a partir da face esquerda do envelope):")
        txt.append(f"      - Roda 1: {VEH_POS_RODAS_M[0]:.2f} m")
        txt.append(f"      - Roda 2: {VEH_POS_RODAS_M[1]:.2f} m")
        txt.append("")

        # SEÇÃO 2 – ZONAS DE CARREGAMENTO
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 2 – DELIMITAÇÃO DAS ZONAS DE CARREGAMENTO          │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Zona rolável (entre faces internas das barreiras NJ):")
        txt.append(f"    x_min = {x_min:.4f} m")
        txt.append(f"    x_max = {x_max:.4f} m")
        txt.append("")
        if tem_passeio:
            txt.append("  Regiões de passeio (onde atua p'):")
            for j, (a, b) in enumerate(regioes_passeio):
                txt.append(f"    Passeio {j+1}: de {a:.4f} a {b:.4f} m")
        else:
            txt.append("  Não há passeios considerados.")
        txt.append("")

        # SEÇÃO 3 – SEÇÃO AA: CARGA DISTRIBUÍDA q1
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 3 – SEÇÃO AA: CARGA DISTRIBUÍDA EQUIVALENTE q₁     │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Para o momento fletor máximo no vão, carrega-se toda a zona")
        txt.append("  rolável com η(x) > 0 pela carga distribuída q.")
        txt.append("")
        txt.append("  q₁_i = q · ∫_{zona rolável, η>0} η(x) dx")
        if tem_passeio:
            txt.append("       + p' · ∫_{passeios, η>0} η(x) dx")
        txt.append("")
        txt.append("  Integração analítica (η é linear, primitiva de grau 2):")
        txt.append("    F(x) = c0·x + (c1/2)·x²")
        txt.append("")
        txt.append("  Resultados por longarina:")
        header_q1 = ["i", "∫η dx_central [m]", "q·∫ [kN/m]"]
        if tem_passeio:
            header_q1 += ["∫η dx_passeio [m]", "p'·∫ [kN/m]"]
        header_q1.append("q₁ [kN/m]")
        fmt_row = "  {i:>3}  {int_c:>18.6f}  {q_int:>10.3f}"  # alterado para .3f
        if tem_passeio:
            fmt_row += "  {int_p:>18.6f}  {p_int:>10.3f}"  # alterado para .3f
        fmt_row += "  {q1:>10.3f}"  # alterado para .3f
        txt.append("  " + " ".join([f"{h:^20}" if len(h)<=20 else h for h in header_q1]))
        txt.append("  " + "-" * (len(header_q1)*12))
        for i in range(1, n+1):
            k = i-1
            vals = {
                'i': i, 'int_c': int_q1[k], 'q_int': q * int_q1[k],
                'q1': q1_vals[k]
            }
            if tem_passeio:
                int_p = self._int_passeio_q1[k]
                vals['int_p'] = int_p
                vals['p_int'] = p_linha * int_p
            txt.append(fmt_row.format(**vals))
        txt.append("")

        # SEÇÃO 4 – SEÇÃO BB: VEÍCULO + q2
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 4 – SEÇÃO BB: POSIÇÃO ÓTIMA DO VEÍCULO (q₂ + Q)    │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Para o esforço cortante máximo no apoio, o veículo é")
        txt.append("  posicionado transversalmente de forma a maximizar a soma")
        txt.append("  da carga concentrada Q com a carga distribuída remanescente q₂.")
        txt.append("")
        txt.append("  Q₁(x_veh) = Q · [ η(x_veh+0.5) + η(x_veh+2.5) ]")
        txt.append("  q₂(x_veh) = q · [ ∫_{x_min}^{x_veh} max(η,0) dx")
        txt.append("                   + ∫_{x_veh+3.0}^{x_max} max(η,0) dx ]")
        if tem_passeio:
            txt.append("            + p' · ∫_{passeios, η>0} η dx")
        txt.append("")
        txt.append("  Varredura numérica com 8000 pontos em x_veh ∈ [x_min, x_max-3.0].")
        txt.append("")
        txt.append("  Resultados da posição ótima para cada longarina:")
        header_bb = ["i", "x_veh [m]", "η_Q1", "η_Q2", "Q [kN]", "∫η dx_q2 [m]", "q·∫ [kN/m]"]
        if tem_passeio:
            header_bb += ["∫η dx_p' [m]", "p'·∫ [kN/m]"]
        header_bb.append("q₂ [kN/m]")
        txt.append("  " + " ".join([f"{h:^12}" for h in header_bb]))
        txt.append("  " + "-" * (len(header_bb)*13))
        for i in range(1, n+1):
            k = i-1
            y1, y2 = y_Q_vals[k]
            row = [
                f"{i:>3}", f"{x_crit[k]:>10.4f}",
                f"{y1:>6.4f}", f"{y2:>6.4f}",
                f"{Q1_vals[k]:>8.3f}",   # alterado para .3f
                f"{int_q2[k]:>12.6f}",
                f"{q * int_q2[k]:>10.3f}"  # alterado para .3f
            ]
            if tem_passeio:
                int_p = self._int_passeio_q2[k]
                row.extend([f"{int_p:>12.6f}", f"{p_linha * int_p:>10.3f}"])  # alterado para .3f
            row.append(f"{q2_vals[k]:>10.3f}")  # alterado para .3f
            txt.append("  " + " ".join(row))
        txt.append("")

        # SEÇÃO 5 – LONGARINA CRÍTICA
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 5 – LONGARINA CRÍTICA (MAIOR q₁ + q₂ + Q)          │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append(f"  Longarina crítica: {crit['longarina']} (i = {crit['longarina']})")
        txt.append(f"    xi = {crit['xi_m']:.4f} m")
        txt.append(f"    Equação LI: {crit['equacao_li']}")
        txt.append(f"    q₁ = {crit['q1_kNm']:.3f} kN/m")  # alterado para .3f
        txt.append(f"    q₂ = {crit['q2_kNm']:.3f} kN/m")  # alterado para .3f
        txt.append(f"    Q  = {crit['Q_kN']:.3f} kN")      # alterado para .3f
        txt.append(f"    Total (q₁+q₂+Q) = {crit['total']:.3f}")  # alterado para .3f
        txt.append(f"    Posição ótima do veículo (x_veh) = {crit['x_critico_m']:.4f} m")
        txt.append("")

        # SEÇÃO 6 – SÍNTESE FINAL
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 6 – SÍNTESE FINAL DOS RESULTADOS                   │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Resumo dos carregamentos equivalentes por longarina:")
        txt.append("")
        tabela_resumo = self.get_tabela_resumo()
        for row in tabela_resumo:
            txt.append("  " + "  ".join([f"{str(c):>15}" for c in row]))
        txt.append("")
        txt.append(SEP_D)
        txt.append("FIM DO MEMORIAL – TREM-TIPO LONGITUDINAL")
        txt.append(SEP_D)

        texto_plano = "\n".join(txt)

        # ─────────────────────────────────────────────────────────────────────
        # HTML (TEMA ESCURO)
        # ─────────────────────────────────────────────────────────────────────
        def badge_crit(i):
            return '<span class="badge-crit">★ CRÍTICA</span>' if i == crit['longarina'] else ''

        # Seção AA (q1)
        header_q1_html = "<tr><th>i</th><th>∫η dx_central [m]</th><th>q·∫ [kN/m]</th>"
        if tem_passeio:
            header_q1_html += "<th>∫η dx_passeio [m]</th><th>p'·∫ [kN/m]</th>"
        header_q1_html += "<th>q₁ [kN/m]</th></tr>"
        rows_q1 = ""
        for i in range(1, n+1):
            k = i-1
            row = f"<tr><td>{i}</td><td>{int_q1[k]:.6f}</td><td>{q * int_q1[k]:.3f}</td>"  # q·∫ com .3f
            if tem_passeio:
                int_p = self._int_passeio_q1[k]
                row += f"<td>{int_p:.6f}</td><td>{p_linha * int_p:.3f}</td>"  # p'·∫ com .3f
            row += f"<td><strong>{q1_vals[k]:.3f}</strong></td></tr>"  # q1 com .3f
            rows_q1 += row

        # Seção BB (q2+Q)
        header_bb_html = "<tr><th>i</th><th>x_veh [m]</th><th>η_Q1</th><th>η_Q2</th><th>Q [kN]</th><th>∫η dx_q2 [m]</th><th>q·∫ [kN/m]</th>"
        if tem_passeio:
            header_bb_html += "<th>∫η dx_p' [m]</th><th>p'·∫ [kN/m]</th>"
        header_bb_html += "<th>q₂ [kN/m]</th></tr>"
        rows_bb = ""
        for i in range(1, n+1):
            k = i-1
            y1, y2 = y_Q_vals[k]
            row = (f"<tr><td>{i}</td><td>{x_crit[k]:.4f}</td><td>{y1:.4f}</td><td>{y2:.4f}</td>"
                f"<td>{Q1_vals[k]:.3f}</td><td>{int_q2[k]:.6f}</td><td>{q * int_q2[k]:.3f}</td>")  # Q e q·∫ com .3f
            if tem_passeio:
                int_p = self._int_passeio_q2[k]
                row += f"<td>{int_p:.6f}</td><td>{p_linha * int_p:.3f}</td>"  # p'·∫ com .3f
            row += f"<td><strong>{q2_vals[k]:.3f}</strong></td></tr>"  # q2 com .3f
            rows_bb += row

        # Tabela resumo final
        tabela_resumo = self.get_tabela_resumo()
        rows_sint = ""
        for row in tabela_resumo[1:]:
            is_crit = (int(row[0]) == crit['longarina'])
            crit_badge = badge_crit(int(row[0])) if is_crit else ""
            rows_sint += f"<tr style='{'background:#1e3a5f;' if is_crit else ''}'>"
            for col in row:
                rows_sint += f"<td>{col}{crit_badge if is_crit and row.index(col)==0 else ''}</td>"
            rows_sint += "</tr>"

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memorial – Trem-Tipo Longitudinal Equivalente</title>
<style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: 'Segoe UI', Tahoma, Geneva, sans-serif;
        background: #0a0f1e;
        color: #dde6f5;
        padding: 24px;
        font-size: 14px;
        line-height: 1.75;
    }}
    .container {{
        max-width: 1350px;
        margin: 0 auto;
        background: #111827;
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 12px 48px rgba(0,0,0,0.7);
        border: 1px solid #1e3a5f;
    }}
    /* ── Cabeçalho ── */
    .header {{
        background: linear-gradient(135deg, #0d1b4b 0%, #1a3272 40%, #0e2257 100%);
        padding: 36px 40px;
        text-align: center;
        border-bottom: 2px solid #2563eb;
        position: relative;
    }}
    .header::after {{
        content: '';
        position: absolute;
        bottom: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, transparent, #f59e0b, #f38ba8, #f59e0b, transparent);
    }}
    .header h1 {{ font-size: 1.65em; font-weight: 700; letter-spacing: 0.4px; color: #e2effe; margin-bottom: 6px; }}
    .header .subtitle {{ font-size: 0.95em; color: #93c5fd; margin-bottom: 4px; }}
    .header .norma {{ font-size: 0.82em; color: #64748b; letter-spacing: 0.5px; }}
    /* ── Índice ── */
    .toc {{
        background: #0f172a;
        padding: 14px 40px;
        border-bottom: 1px solid #1e293b;
        font-size: 0.82em;
        color: #64748b;
    }}
    .toc a {{ color: #60a5fa; text-decoration: none; margin: 0 6px; }}
    .toc a:hover {{ text-decoration: underline; }}
    /* ── Conteúdo ── */
    .content {{ padding: 36px 40px; }}
    /* ── Seções ── */
    .section {{
        margin-bottom: 36px;
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #1e3a5f;
    }}
    .section-header {{
        background: linear-gradient(90deg, #1e3a5f, #172040);
        padding: 14px 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .section-number {{
        background: #2563eb;
        color: white;
        font-size: 0.78em;
        font-weight: 700;
        padding: 3px 9px;
        border-radius: 20px;
        white-space: nowrap;
    }}
    .section-title {{
        font-size: 1.05em;
        font-weight: 700;
        color: #93c5fd;
        letter-spacing: 0.2px;
    }}
    .section-body {{
        padding: 20px 24px;
        background: rgba(17,24,39,0.6);
    }}
    .section-body p {{ margin-bottom: 10px; color: #cbd5e1; }}
    .section-body p:last-child {{ margin-bottom: 0; }}
    .section-body ul {{ margin: 8px 0 8px 22px; color: #cbd5e1; }}
    .section-body li {{ margin-bottom: 5px; }}
    /* ── Fórmulas ── */
    .formula-block {{
        background: #0a0f1e;
        border-left: 4px solid #f59e0b;
        border-radius: 0 8px 8px 0;
        padding: 14px 20px;
        margin: 14px 0;
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.93em;
        color: #fef3c7;
        white-space: pre-wrap;
        line-height: 1.9;
    }}
    /* ── Resultado destaque ── */
    .result-box {{
        background: #0c1a30;
        border: 1px solid #2563eb;
        border-radius: 8px;
        padding: 14px 18px;
        margin: 14px 0;
        color: #93c5fd;
        font-size: 1.0em;
    }}
    .result-box strong {{ color: #60a5fa; }}
    /* ── Badge longarina crítica ── */
    .badge-crit {{
        background: linear-gradient(90deg, #92400e, #b45309);
        color: #fde68a;
        padding: 2px 12px;
        border-radius: 12px;
        font-size: 0.79em;
        font-weight: 700;
        margin-left: 8px;
        white-space: nowrap;
    }}
    /* ── Caixa resultado crítico ── */
    .crit-box {{
        background: linear-gradient(135deg, #0c1a30, #1a2c1a);
        border: 2px solid #f59e0b;
        border-radius: 10px;
        padding: 18px 22px;
        margin: 14px 0;
    }}
    .crit-box h3 {{ color: #fbbf24; margin-bottom: 10px; font-size: 1.1em; }}
    .crit-val {{ font-size: 1.3em; font-weight: 700; color: #34d399; }}
    /* ── Nota ── */
    .section-note {{
        background: rgba(251,191,36,0.08);
        border-left: 3px solid #f59e0b;
        border-radius: 0 6px 6px 0;
        padding: 10px 14px;
        margin-top: 14px;
        font-size: 0.88em;
        color: #fde68a;
    }}
    /* ── Tabelas ── */
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.85em; }}
    thead th {{
        background: #1e3a5f;
        color: #93c5fd;
        padding: 9px 10px;
        text-align: center;
        border-bottom: 2px solid #2563eb;
        font-weight: 700;
        letter-spacing: 0.2px;
        white-space: nowrap;
    }}
    tbody td {{
        padding: 7px 10px;
        border-bottom: 1px solid #1e293b;
        text-align: center;
        color: #cbd5e1;
    }}
    tbody tr:hover td {{ background: rgba(59,130,246,0.07); }}
    .tr-crit td {{ background: rgba(245,158,11,0.08) !important; }}
    .tr-crit td strong {{ color: #fbbf24; }}
    tbody td:first-child {{ font-weight: 700; color: #60a5fa; }}
    /* ── Param table ── */
    .param-table td {{ text-align: left !important; padding: 7px 12px; }}
    .param-table td:first-child {{ color: #94a3b8 !important; font-weight: normal !important; width: 55%; }}
    .param-table td:last-child {{ color: #e2e8f0; font-weight: 600; text-align: right !important; }}
    /* ── Footer ── */
    .footer {{
        background: #0a0f1e;
        padding: 18px 40px;
        border-top: 1px solid #1e293b;
        text-align: center;
        color: #475569;
        font-size: 0.80em;
        line-height: 1.6;
    }}
    code {{ background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #fbbf24; font-family: 'Courier New', monospace; font-size: 0.91em; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 14px; }}
    .mini-stat {{ background: #0f172a; border: 1px solid #1e3a5f; border-radius: 8px; padding: 12px 16px; text-align: center; }}
    .mini-stat .label {{ font-size: 0.78em; color: #64748b; margin-bottom: 4px; }}
    .mini-stat .value {{ font-size: 1.25em; font-weight: 700; color: #60a5fa; }}
</style>
</head>
<body>
<div class="container">

  <!-- ══ Cabeçalho ══════════════════════════════════════════════════════ -->
  <div class="header">
    <h1>🚛 Memorial de Cálculo — Trem-Tipo Longitudinal Equivalente</h1>
    <p class="subtitle">Cargas q₁, q₂ e Q por Longarina · Método de Engesser-Courbon · NBR 7188:2013</p>
    <p class="norma">Integração Analítica (Seção AA) · Varredura Numérica — 8 000 pontos (Seção BB) · Gerado automaticamente</p>
  </div>

  <!-- ══ Índice ══════════════════════════════════════════════════════════ -->
  <div class="toc">
    ▸ Seções:
    <a href="#s1">1 – Carregamento</a> ·
    <a href="#s2">2 – Zonas</a> ·
    <a href="#s3">3 – Seção AA (q₁)</a> ·
    <a href="#s4">4 – Seção BB (q₂+Q)</a> ·
    <a href="#s5">5 – Longarina Crítica</a> ·
    <a href="#s6">6 – Síntese Final</a>
  </div>

  <div class="content">

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s1">
      <div class="section-header">
        <span class="section-number">SEÇÃO 1</span>
        <span class="section-title">📌 Carregamento Móvel — Dados do Trem-Tipo (NBR 7188:2013)</span>
      </div>
      <div class="section-body">
        <p>
          O trem-tipo adotado na NBR 7188:2013 é composto por um <strong>veículo-tipo</strong>
          (carga concentrada Q em cada ponto de aplicação) e uma <strong>carga distribuída
          de multidão</strong> (q por metro quadrado de pista) que preenche a zona rolável
          restante. A classe da via determina os valores de Q e q, conforme tabela normativa.
        </p>
        <table class="param-table">
          <tbody>
            <tr><td>Classe da via (NBR 7188:2013)</td><td>{classe}</td></tr>
            <tr><td>Carga concentrada por ponto de aplicação — Q</td><td>{Q:.2f} kN</td></tr>
            <tr><td>Carga distribuída de multidão na pista — q</td><td>{q:.4f} kN/m · m⁻¹ (por metro de largura)</td></tr>
            <tr><td>Carga distribuída nos passeios — p'</td><td>{p_linha:.4f} kN/m · m⁻¹ {'(passeio presente)' if tem_passeio else '(sem passeio ativo)'}</td></tr>
          </tbody>
        </table>
        <p style="margin-top:12px;"><strong>Veículo-tipo padrão:</strong></p>
        <table class="param-table">
          <tbody>
            <tr><td>Envelope transversal do veículo</td><td>{VEH_COMPRIMENTO_M:.2f} m</td></tr>
            <tr><td>Posição da Roda 1 (da face esquerda do envelope)</td><td>{VEH_POS_RODAS_M[0]:.2f} m</td></tr>
            <tr><td>Posição da Roda 2 (da face esquerda do envelope)</td><td>{VEH_POS_RODAS_M[1]:.2f} m</td></tr>
            <tr><td>Distância entre rodas</td><td>{VEH_POS_RODAS_M[1]-VEH_POS_RODAS_M[0]:.2f} m</td></tr>
          </tbody>
        </table>
        <div class="section-note">
          ⚠️ O coeficiente de impacto e os fatores de redução de faixas devem ser aplicados
          na análise longitudinal (vão a vão), <strong>não</strong> nesta fase de distribuição
          transversal pelo Método de Courbon.
        </div>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s2">
      <div class="section-header">
        <span class="section-number">SEÇÃO 2</span>
        <span class="section-title">🚧 Delimitação das Zonas de Carregamento Transversal</span>
      </div>
      <div class="section-body">
        <p>
          A zona rolável (ou pista de rolamento) é a faixa transversal disponível para
          posicionamento de veículos e cargas distribuídas. Seus limites são as
          <strong>faces internas das barreiras New Jersey (NJ)</strong>, com largura de
          {NJ_LARGURA_CM:.0f} cm cada. As coordenadas são medidas em relação ao centro
          elástico x₀ (positivo para a direita).
        </p>
        <div class="formula-block">Zona rolável:  x ∈ [{x_min:.4f} m,  {x_max:.4f} m]
Largura rolável útil: {x_max - x_min:.4f} m

{'Passeios ativos (p'' = ' + str(p_linha) + ' kN/m²):' if tem_passeio else 'Passeios: ausentes ou p'' = 0'}
{chr(10).join([f'  Passeio {j+1}: x ∈ [{a:.4f} m, {b:.4f} m]  (largura {b-a:.4f} m)' for j,(a,b) in enumerate(self._regioes_passeio)]) if tem_passeio else '  Nenhum passeio carregado.'}</div>
        <p>
          Para a Seção BB, o veículo (envelope de {VEH_COMPRIMENTO_M:.2f} m) pode ser posicionado em
          x_veh ∈ [{x_min:.4f}, {x_max - VEH_COMPRIMENTO_M:.4f}] m,
          varrendo <strong>8 000 posições discretas</strong> para localizar o ponto de máximo efeito.
        </p>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s3">
      <div class="section-header">
        <span class="section-number">SEÇÃO 3</span>
        <span class="section-title">📊 Seção AA — Carga Distribuída Equivalente q₁ (Momento Máximo)</span>
      </div>
      <div class="section-body">
        <p>
          A <strong>Seção AA</strong> corresponde à seção de máximo momento fletor positivo
          no vão. Para este estado limite, <em>toda</em> a zona rolável com ordenada η(x) &gt; 0
          é preenchida pela carga distribuída q. A carga equivalente por longarina é obtida
          pela integração analítica da LI (polinômio de grau 2) sobre a região positiva:
        </p>
        <div class="formula-block">q₁_i = q · ∫_{{zona rolável, η>0}} η_i(x) dx{' + p'' · ∫_{{passeios, η>0}} η_i(x) dx' if tem_passeio else ''}   [kN/m]

Integral analítica com primitiva:
    F(x) = c₀·x + (c₁/2)·x²
    onde  c₀ = 1/n  e  c₁ = xi/Σxi²

Domínio de integração:
    η_i(x) ≥ 0  em  x ∈ [max(x_zero, x_min), x_max]   (se c₁ > 0)
    η_i(x) ≥ 0  em  x ∈ [x_min, min(x_zero, x_max)]   (se c₁ < 0)</div>
        <table>
          <thead>
            <tr>
              <th>Longarina i</th>
              <th>∫η dx — zona central [m]</th>
              <th>q · ∫ [kN/m]</th>
              {'<th>∫η dx — passeio [m]</th><th>p\' · ∫ [kN/m]</th>' if tem_passeio else ''}
              <th><strong>q₁ [kN/m]</strong></th>
            </tr>
          </thead>
          <tbody>{rows_q1}</tbody>
        </table>
        <div class="section-note">
          📌 A integração é <strong>analítica e exata</strong> — não há erro de discretização.
          O zero da LI (onde η cruza o eixo x) é calculado como x_zero = −c₀/c₁, determinando
          o limite preciso da região positiva dentro da zona rolável.
        </div>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s4">
      <div class="section-header">
        <span class="section-number">SEÇÃO 4</span>
        <span class="section-title">🚛 Seção BB — Posição Ótima do Veículo e Cargas q₂ + Q (Cortante Máximo)</span>
      </div>
      <div class="section-body">
        <p>
          A <strong>Seção BB</strong> corresponde ao máximo esforço cortante na seção junto
          ao apoio. O veículo-tipo é varrido transversalmente em 8 000 posições discretas
          para encontrar a posição x_veh que maximiza a soma <em>q₂ + Q</em>:
        </p>
        <div class="formula-block">Para cada posição transversal x_veh do veículo:

  Q(x_veh) = Q_kN · [ η_i(x_veh + {VEH_POS_RODAS_M[0]:.2f}) + η_i(x_veh + {VEH_POS_RODAS_M[1]:.2f}) ]   [kN]

  q₂(x_veh) = q · {{ ∫_{{x_min}}^{{x_veh}}        max(η_i, 0) dx
                     + ∫_{{x_veh+{VEH_COMPRIMENTO_M:.2f}}}^{{x_max}}  max(η_i, 0) dx }}{' + p'' · ∫_{{passeios, η>0}} η_i dx' if tem_passeio else ''}  [kN/m]

  Função-objetivo: maximizar  f(x_veh) = q₂(x_veh) + Q(x_veh)

  Domínio:  x_veh ∈ [{x_min:.4f} m,  {x_max - VEH_COMPRIMENTO_M:.4f} m]</div>
        <p>
          As cargas concentradas Q nas posições das rodas são ponderadas pelas ordenadas η
          da LI naqueles pontos. O somatório de Q pode incluir valores negativos de η
          (alívio), pois o objetivo é encontrar a posição globalmente mais desfavorável.
          A carga distribuída q₂, contudo, integra apenas η &gt; 0.
        </p>
        <table>
          <thead>
            <tr>
              <th>Long. i</th>
              <th>x_veh ótimo [m]</th>
              <th>η(x_Q1)</th>
              <th>η(x_Q2)</th>
              <th>Q [kN]</th>
              <th>∫η dx — q₂ [m]</th>
              <th>q · ∫ [kN/m]</th>
              {'<th>∫η dx — p\' [m]</th><th>p\' · ∫ [kN/m]</th>' if tem_passeio else ''}
              <th><strong>q₂ [kN/m]</strong></th>
            </tr>
          </thead>
          <tbody>{rows_bb}</tbody>
        </table>
        <div class="section-note">
          📌 A integral de q₂ é calculada <strong>analiticamente</strong> para cada posição x_veh
          da varredura numérica. A varredura em 8 000 pontos garante resolução espacial de
          Δx ≈ {(x_max - VEH_COMPRIMENTO_M - x_min) / 8000 * 1000:.2f} mm, suficiente para a precisão de engenharia exigida.
        </div>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s5">
      <div class="section-header">
        <span class="section-number">SEÇÃO 5</span>
        <span class="section-title">🎯 Longarina Crítica — Maior Solicitação Total (q₁ + q₂ + Q)</span>
      </div>
      <div class="section-body">
        <p>
          A longarina crítica é identificada como aquela que apresenta o maior valor da soma
          <strong>q₁ + q₂ + Q</strong>. Por ser a mais solicitada transversalmente, deve
          receber o trem-tipo longitudinal de maior intensidade no dimensionamento.
        </p>
        <div class="crit-box">
          <h3>🏆 Longarina {crit['longarina']} — <span class="badge-crit">MAIS SOLICITADA</span></h3>
          <p style="color:#93c5fd; margin-bottom: 12px;"><code>{crit['equacao_li']}</code>
             &nbsp;|&nbsp; xi = {crit['xi_m']:.4f} m &nbsp;|&nbsp; xi² = {crit['xi2_m2']:.4f} m²</p>
          <div class="grid-2">
            <div class="mini-stat">
              <div class="label">q₁ — Seção AA</div>
              <div class="value">{crit['q1_kNm']:.3f} kN/m</div>
            </div>
            <div class="mini-stat">
              <div class="label">q₂ — Seção BB</div>
              <div class="value">{crit['q2_kNm']:.3f} kN/m</div>
            </div>
            <div class="mini-stat">
              <div class="label">Q — Carga concentrada BB</div>
              <div class="value">{crit['Q_kN']:.3f} kN</div>
            </div>
            <div class="mini-stat" style="border-color:#f59e0b;">
              <div class="label">Total q₁ + q₂ + Q</div>
              <div class="value" style="color:#fbbf24;">{crit['total']:.3f}</div>
            </div>
          </div>
          <p style="margin-top: 14px; color: #94a3b8; font-size: 0.88em;">
            Posição ótima do veículo: x_veh = <strong style="color:#93c5fd;">{crit['x_critico_m']:.4f} m</strong>
            em relação ao centro elástico.
          </p>
        </div>
      </div>
    </div>

    <!-- ─────────────────────────────────────────────────────────────────── -->
    <div class="section" id="s6">
      <div class="section-header">
        <span class="section-number">SEÇÃO 6</span>
        <span class="section-title">📋 Síntese Final — Resumo dos Carregamentos por Longarina</span>
      </div>
      <div class="section-body">
        <p>
          A tabela abaixo reúne, para cada longarina, a equação da Linha de Influência
          e os carregamentos equivalentes finais (q₁, q₂, Q) para uso direto na análise
          longitudinal da estrutura.
        </p>
        <table>
          <thead>
            <tr>
              <th>i</th>
              <th>xi [m]</th>
              <th>xi² [m²]</th>
              <th>η_i(x) — Linha de Influência</th>
              <th>q₁ [kN/m]</th>
              <th>q₂ [kN/m]</th>
              <th>Q [kN]</th>
            </tr>
          </thead>
          <tbody>{rows_sint}</tbody>
        </table>
        <div class="result-box" style="margin-top:16px;">
          <strong>Verificação de simetria:</strong> Para estruturas com longarinas igualmente
          espaçadas e simétricas em relação ao centro elástico, longarinas opostas (L1↔Ln,
          L2↔L(n-1), etc.) devem apresentar valores idênticos de q₁, q₂ e Q.
          Divergências indicam inconsistência na geometria de entrada ou nos limites das zonas.
        </div>
        <div class="section-note">
          📐 Estes valores de q₁, q₂ e Q são as <em>intensidades por unidade de comprimento</em>
          a aplicar na análise longitudinal de cada longarina individualmente,
          substituindo o carregamento original do trem-tipo pela parcela que cabe a cada
          elemento estrutural — conforme preconiza o Método de Engesser-Courbon.
        </div>
      </div>
    </div>

  </div><!-- /content -->

  <div class="footer">
    Memorial de Cálculo – Trem-Tipo Longitudinal Equivalente
    &nbsp;·&nbsp; Método de Engesser-Courbon
    &nbsp;·&nbsp; NBR 7188:2013
    &nbsp;·&nbsp; Gerado automaticamente pelo módulo <code>Calculadora_Trem_Tipo_Longarina</code>
  </div>

</div><!-- /container -->
</body>
</html>"""

        return texto_plano, html