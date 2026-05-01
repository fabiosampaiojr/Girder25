# ============================================================================
# CALCULADORA_COEFICIENTE_IMPACTO.PY
# Cálculo e Visualização dos Coeficientes de Impacto — NBR 7188:2013
# ============================================================================
"""
Módulo para cálculo e visualização dos coeficientes de impacto de pontes e
viadutos conforme a norma brasileira ABNT NBR 7188:2013 (Carga móvel rodoviária
e de pedestres em pontes, viadutos, passarelas e outras estruturas).

─────────────────────────────────────────────────────────────────────────────
COEFICIENTES IMPLEMENTADOS
─────────────────────────────────────────────────────────────────────────────
  CIA  — Coeficiente de Impacto Adicional        (NBR 7188:2013 §5.1.2.3)
  CIV  — Coeficiente de Impacto Vertical         (NBR 7188:2013 §5.1.2.1)
  CNF  — Coeficiente do Número de Faixas         (NBR 7188:2013 §5.1.2.2)
  φ    — Coeficiente de Impacto Total = CIA · CIV · CNF

─────────────────────────────────────────────────────────────────────────────
USO TÍPICO
─────────────────────────────────────────────────────────────────────────────
  from modules.Calculadora_Coeficiente_Impacto import (
      CalculadoraCoeficienteImpacto,
  )

  calc = CalculadoraCoeficienteImpacto(superestrutura, secao_transversal)
  calc.imprimir_resumo()

─────────────────────────────────────────────────────────────────────────────
SISTEMA DE COORDENADAS
─────────────────────────────────────────────────────────────────────────────
  CÁLCULO (dicionários de zonas):
    Coordenadas reais em metros, sem gaps.
    Para 'biapoiada': vão 1 = [0, v1], vão 2 = [v1, v1+v2], etc.
    As juntas de dilatação ficam nas fronteiras reais dos vãos.
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Union


# ============================================================================
# CONSTANTES NORMATIVAS — NBR 7188:2013
# ============================================================================

# CIA — §5.1.2.3
CIA_NORMAL: float          = 1.00   # Fora da zona de influência da junta
CIA_CONCRETO_MISTA: float  = 1.25   # Concreto ou misto, dentro de 5 m da junta
CIA_ACO: float             = 1.15   # Aço, dentro de 5 m da junta
LIMIAR_CIA_M: float        = 5.0    # Distância de influência da junta [m]

# CNF — §5.1.2.2
# Simplificação: N deduzido da classe da via.
#   "0" / "I - A" (pista dupla)  → N = 4 → CNF = 0,90
#   Demais classes (pista simples) → N = 2 → CNF = 1,00
CLASSES_PISTA_DUPLA: Tuple[str, ...] = ("0", "I - A")

# Mapeamento ComboBox → identificador interno
MAPA_TIPOS: Dict[str, str] = {
    "Isostática: Múltiplos Vãos Biapoioados":  "biapoiada",
    "Isostática: Biapoiada com Balanço":        "isostatica_em_balanco",
    "Hiperestática: Vão Contínuo sem Balanço":  "hiperestatica_sem_balanco",
    "Hiperestática: Vão Contínuo com Balanço":  "hiperestatica_com_balanco",
}

# Tema visual — compatível com desenho_dcl.py
COR_FUNDO: str = "#2b2b2b"
COR_OBJ: str   = "white"

# Paleta de cores dos gráficos
CORES_COEF: Dict[str, str] = {
    "CIA":     "#FF7043",
    "CIV":     "#42A5F5",
    "CNF":     "#66BB6A",
    "IMPACTO": "#FFA726",
}


# ============================================================================
# ESTRUTURA DE DADO: SEGMENTO ESTRUTURAL
# ============================================================================

class SegmentoEstrutural:
    """
    Trecho contíguo da estrutura com propriedades uniformes de CIV.

    As coordenadas x_ini / x_fim são sempre REAIS (sem gaps visuais),
    inclusive para o tipo 'biapoiada'. Os gaps aparecem somente no desenho.

    Atributos
    ─────────
    x_ini : coordenada real de início [m]
    x_fim : coordenada real de fim    [m]
    tipo  : 'laje' | 'vao_iso' | 'balanco' | 'vao_cont'
    liv   : vão de inércia para cálculo do CIV [m]
    """

    __slots__ = ("x_ini", "x_fim", "tipo", "liv")

    def __init__(self, x_ini: float, x_fim: float, tipo: str, liv: float) -> None:
        self.x_ini = x_ini
        self.x_fim = x_fim
        self.tipo  = tipo
        self.liv   = liv

    @property
    def comprimento(self) -> float:
        return self.x_fim - self.x_ini

    def __repr__(self) -> str:
        return (
            f"Segmento({self.tipo!r}, "
            f"x=[{self.x_ini:.2f}, {self.x_fim:.2f}] m, "
            f"Liv={self.liv:.2f} m)"
        )


# ============================================================================
# CALCULADORA PRINCIPAL
# ============================================================================

class CalculadoraCoeficienteImpacto:
    """
    Calcula os coeficientes de impacto (NBR 7188:2013) por zonas ao longo
    da extensão longitudinal da estrutura.

    Parâmetros
    ──────────
    superestrutura     : objeto Superestrutura  (Gerenciador_Dados.py)
    secao_transversal  : objeto SecaoTransversal (Gerenciador_Dados.py)
    material           : 'concreto_mista' (padrão) | 'aco'

    Resultados públicos
    ───────────────────
    Dicionários {(x_ini, x_fim): valor}, coordenadas em metros (reais, sem gap).
    Intervalos consecutivos de mesmo valor são fundidos (_merge_zonas).
    Valores arredondados a 3 casas decimais.

        zonas_cia      : {(x_ini, x_fim): CIA}
        zonas_civ      : {(x_ini, x_fim): CIV}
        zonas_cnf      : {(x_ini, x_fim): CNF}
        zonas_impacto  : {(x_ini, x_fim): φ}
    """

    def __init__(
        self,
        superestrutura,
        secao_transversal,
        material: str = "concreto_mista",
    ) -> None:
        self.sup      = superestrutura
        self.sec      = secao_transversal
        self.material = material.lower().replace(" ", "_")

        self._tipo: str                = self._normalizar_tipo(superestrutura.tipo)
        self._vaos: List[float]        = list(superestrutura.vaos)
        self._laje: Union[float, bool] = superestrutura.laje_transicao

        # Fator de escala (baseado em comprimentos reais, idêntico a desenho_dcl.py)
        self._fator: float = self._calcular_fator_escala()
        # Gap VISUAL entre vãos biapoiados — usado exclusivamente no desenho do DCL
        self._gap: float = 0.45 * self._fator

        # Resultados públicos (populados por _calcular_zonas)
        self.zonas_cia:     Dict[Tuple[float, float], float] = {}
        self.zonas_civ:     Dict[Tuple[float, float], float] = {}
        self.zonas_cnf:     Dict[Tuple[float, float], float] = {}
        self.zonas_impacto: Dict[Tuple[float, float], float] = {}

        # Geometria real (sem gaps)
        self._segmentos: List[SegmentoEstrutural] = self._construir_segmentos()
        self._juntas:    List[float]              = self._obter_posicoes_juntas()

        self._calcular_zonas()

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRIA (COORDENADAS REAIS)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalizar_tipo(texto: str) -> str:
        if texto in MAPA_TIPOS:
            return MAPA_TIPOS[texto]
        if "Múltiplos" in texto or ("Biapoiada" in texto and "Balanço" not in texto):
            return "biapoiada"
        if "Isostática" in texto and "Balanço" in texto:
            return "isostatica_em_balanco"
        if "sem Balanço" in texto:
            return "hiperestatica_sem_balanco"
        if "com Balanço" in texto:
            return "hiperestatica_com_balanco"
        return "biapoiada"

    def _calcular_fator_escala(self) -> float:
        """
        Fator de escala visual baseado no comprimento real total da estrutura.
        Replicação exata da lógica de desenho_dcl.py (sem gaps).
        """
        v, t, lj = self._vaos, self._tipo, self._laje
        if t == "isostatica_em_balanco":
            soma = v[0] + 2 * v[1]
        elif t in ("hiperestatica_sem_balanco", "hiperestatica_com_balanco"):
            soma = v[0] + 2 * v[1] + (2 * v[2] if t == "hiperestatica_com_balanco" else 0)
        else:
            soma = sum(v)
        return max(0.5, (soma + (2 * lj if lj else 0)) / 20.0)

    def _construir_segmentos(self) -> List[SegmentoEstrutural]:
        """
        Constrói segmentos em COORDENADAS REAIS (sem gaps visuais).

        Para 'biapoiada': vãos contíguos — vão i termina onde vão i+1 começa.
        A junta de dilatação existe fisicamente nessa fronteira e é mapeada
        por _obter_posicoes_juntas(); não há espaço real entre as vigas.

        Vão de inércia Liv (NBR 7188:2013 §5.1.2.1):
          • Isostático  → Liv = comprimento do vão
          • Contínuo    → Liv = média aritmética dos vãos contínuos
          • Balanço     → Liv = comprimento do balanço
          • Laje        → Liv = comprimento da laje
        """
        segs: List[SegmentoEstrutural] = []
        x = 0.0
        v, t, lj = self._vaos, self._tipo, self._laje

        if lj:
            segs.append(SegmentoEstrutural(x, x + lj, "laje", float(lj)))
            x += lj

        if t == "biapoiada":
            for vi in v:
                segs.append(SegmentoEstrutural(x, x + vi, "vao_iso", vi))
                x += vi   # sem gap — vãos contíguos nas coordenadas reais

        elif t == "isostatica_em_balanco":
            vc, vb = v[0], v[1]
            segs += [
                SegmentoEstrutural(x,           x + vb,        "balanco", vb),
                SegmentoEstrutural(x + vb,      x + vb + vc,   "vao_iso", vc),
                SegmentoEstrutural(x + vb + vc, x + 2*vb + vc, "balanco", vb),
            ]
            x += 2 * vb + vc

        elif t == "hiperestatica_sem_balanco":
            vc, ve = v[0], v[1]
            liv = (vc + 2 * ve) / 3.0
            segs += [
                SegmentoEstrutural(x,           x + ve,        "vao_cont", liv),
                SegmentoEstrutural(x + ve,      x + ve + vc,   "vao_cont", liv),
                SegmentoEstrutural(x + ve + vc, x + 2*ve + vc, "vao_cont", liv),
            ]
            x += 2 * ve + vc

        elif t == "hiperestatica_com_balanco":
            vc, ve, vb = v[0], v[1], v[2]
            liv_cont = (vc + 2 * ve) / 3.0
            p = [x, x+vb, x+vb+ve, x+vb+ve+vc, x+vb+2*ve+vc, x+2*vb+2*ve+vc]
            segs += [
                SegmentoEstrutural(p[0], p[1], "balanco",  vb),
                SegmentoEstrutural(p[1], p[2], "vao_cont", liv_cont),
                SegmentoEstrutural(p[2], p[3], "vao_cont", liv_cont),
                SegmentoEstrutural(p[3], p[4], "vao_cont", liv_cont),
                SegmentoEstrutural(p[4], p[5], "balanco",  vb),
            ]
            x = p[5]

        if lj:
            segs.append(SegmentoEstrutural(x, x + lj, "laje", float(lj)))

        return segs

    def _obter_posicoes_juntas(self) -> List[float]:
        """
        Identifica coordenadas reais x das juntas de dilatação.

        Critérios (NBR 7188:2013 §5.1.2.3):

        biapoiada:
          Junta em ambas as extremidades de cada vão independente.
          Como os vãos são contíguos nas coord. reais, as juntas ficam em
          0, v1, v1+v2, ..., soma(v). Lajes acrescentam seus próprios limites.

        Demais tipos (estrutura contínua):
          Juntas apenas nas extremidades livres da estrutura.
          Lajes de transição acrescentam a rótula (interface laje-viga) e a
          extremidade exterior (apoio final da laje) como juntas adicionais.
        """
        juntas: set = set()

        if self._tipo == "biapoiada":
            for s in self._segmentos:
                if s.tipo == "vao_iso":
                    juntas.add(s.x_ini)
                    juntas.add(s.x_fim)
                elif s.tipo == "laje":
                    juntas.add(s.x_ini)
                    juntas.add(s.x_fim)
        else:
            if self._segmentos:
                juntas.add(self._segmentos[0].x_ini)
                juntas.add(self._segmentos[-1].x_fim)
            for s in self._segmentos:
                if s.tipo == "laje":
                    juntas.add(s.x_ini)
                    juntas.add(s.x_fim)

        return sorted(juntas)

    # ─────────────────────────────────────────────────────────────────────────
    # CÁLCULO DOS COEFICIENTES
    # ─────────────────────────────────────────────────────────────────────────

    def _cia_em_ponto(self, x: float) -> float:
        """CIA num ponto x: retorna CIA_JUNTA se distância até a junta mais próxima < 5 m."""
        val_junta = CIA_CONCRETO_MISTA if self.material == "concreto_mista" else CIA_ACO
        return val_junta if any(abs(x - j) < LIMIAR_CIA_M for j in self._juntas) else CIA_NORMAL

    @staticmethod
    def _civ_de_liv(liv: float) -> float:
        """
        CIV a partir do vão de inércia Liv (NBR 7188:2013 §5.1.2.1).
            Liv < 10 m         → 1,35
            10 ≤ Liv ≤ 200 m   → 1 + 1,06 · (20 / (Liv + 50))
            Liv > 200 m        → ValueError (exige estudo específico)
        """
        if liv < 10.0:
            return 1.35
        if liv <= 200.0:
            return 1.0 + 1.06 * (20.0 / (liv + 50.0))
        raise ValueError(
            f"Vão de inércia Liv = {liv:.1f} m excede 200 m. "
            "A NBR 7188:2013 §5.1.2.1 exige estudo específico."
        )

    def _cnf(self) -> float:
        """
        CNF (NBR 7188:2013 §5.1.2.2).
        Pista dupla → N=4 → 0,90.   Pista simples → N=2 → 1,00.
        """
        return 0.90 if self.sec.is_pista_dupla() else 1.00

    @staticmethod
    def _merge_zonas(
        zonas: Dict[Tuple[float, float], float]
    ) -> Dict[Tuple[float, float], float]:
        """
        Funde intervalos consecutivos com o mesmo valor (após arredondamento).

        Exemplo:
            {(0,5): 1.25, (5,10): 1.25, (10,20): 1.00, (20,21): 1.00}
            →  {(0,10): 1.25, (10,21): 1.00}

        Dois intervalos são fundidos quando:
          1. São adjacentes: x_fim do anterior ≈ x_ini do próximo (tolerância 1e-9).
          2. Possuem o mesmo valor (comparação exata após arredondamento).
        """
        if not zonas:
            return {}

        items = sorted(zonas.items())           # ordena por (x_ini, x_fim)
        merged: Dict[Tuple[float, float], float] = {}

        xi_curr, xf_curr = items[0][0]
        val_curr          = items[0][1]

        for (xi, xf), val in items[1:]:
            if abs(xi - xf_curr) < 1e-9 and val == val_curr:
                xf_curr = xf            # estende o intervalo corrente
            else:
                merged[(xi_curr, xf_curr)] = val_curr
                xi_curr, xf_curr = xi, xf
                val_curr          = val

        merged[(xi_curr, xf_curr)] = val_curr
        return merged

    def _calcular_zonas(self) -> None:
        """
        Preenche os quatro dicionários de zonas.

        Algoritmo por segmento
        ──────────────────────
        1. CIV: constante no segmento (determinado pelo Liv).
        2. CNF: constante em toda a estrutura.
        3. CIA: pode variar dentro do segmento. Determina-se os breakpoints
           (junta ± LIMIAR_CIA_M) que caem dentro do segmento e subdivide-o.
           O CIA de cada sub-intervalo é avaliado pelo centroide (por construção,
           o centroide é inteiramente de um lado de qualquer limiar de junta).
        4. φ = CIA · CIV · CNF.

        Após montar os dicts brutos, cada um passa por _merge_zonas() para
        fundir trechos consecutivos de mesmo valor.  Todos os valores são
        arredondados a 3 casas decimais.
        """
        cnf = self._cnf()

        cia_raw:     Dict[Tuple[float, float], float] = {}
        civ_raw:     Dict[Tuple[float, float], float] = {}
        cnf_raw:     Dict[Tuple[float, float], float] = {}
        impacto_raw: Dict[Tuple[float, float], float] = {}

        for seg in self._segmentos:
            civ = self._civ_de_liv(seg.liv)

            # Breakpoints para subdivisão do CIA dentro do segmento
            bps: set = {seg.x_ini, seg.x_fim}
            for j in self._juntas:
                for delta in (-LIMIAR_CIA_M, +LIMIAR_CIA_M):
                    bp = j + delta
                    if seg.x_ini < bp < seg.x_fim:
                        bps.add(bp)

            for k, (xi, xf) in enumerate(zip(sorted(bps), sorted(bps)[1:])):
                if xf - xi < 1e-9:
                    continue
                cia = self._cia_em_ponto((xi + xf) / 2.0)
                phi = cia * civ * cnf

                cia_raw    [(xi, xf)] = round(cia, 3)
                civ_raw    [(xi, xf)] = round(civ, 3)
                cnf_raw    [(xi, xf)] = round(cnf, 3)
                impacto_raw[(xi, xf)] = round(phi, 3)

        # Merge: funde intervalos consecutivos de mesmo valor
        self.zonas_cia     = self._merge_zonas(cia_raw)
        self.zonas_civ     = self._merge_zonas(civ_raw)
        self.zonas_cnf     = self._merge_zonas(cnf_raw)
        self.zonas_impacto = self._merge_zonas(impacto_raw)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERFACE PÚBLICA
    # ─────────────────────────────────────────────────────────────────────────

    def get_zonas(self, coef: str) -> Dict[Tuple[float, float], float]:
        """Retorna o dicionário de zonas. coef: 'CIA'|'CIV'|'CNF'|'Impacto' (case-insensitive)."""
        despacho = {
            "CIA":     self.zonas_cia,
            "CIV":     self.zonas_civ,
            "CNF":     self.zonas_cnf,
            "IMPACTO": self.zonas_impacto,
            "PHI":     self.zonas_impacto,
        }
        chave = coef.strip().upper()
        if chave not in despacho:
            raise ValueError(f"Coeficiente desconhecido: {coef!r}. Use 'CIA', 'CIV', 'CNF' ou 'Impacto'.")
        return despacho[chave]

    def resumo(self) -> Dict:
        """Dicionário com resumo completo dos resultados."""
        phi_vals = list(self.zonas_impacto.values())
        return {
            "tipo_estrutural": self._tipo,
            "material":        self.material,
            "classe_via":      self.sec.classe,
            "CNF":             self._cnf(),
            "juntas_x_m":      self._juntas,
            "phi_min":         min(phi_vals) if phi_vals else None,
            "phi_max":         max(phi_vals) if phi_vals else None,
            "zonas_cia":       self.zonas_cia,
            "zonas_civ":       self.zonas_civ,
            "zonas_cnf":       self.zonas_cnf,
            "zonas_impacto":   self.zonas_impacto,
        }

    def imprimir_resumo(self) -> None:
        """Imprime os resultados no console."""
        r   = self.resumo()
        sep = "─" * 62
        print(sep)
        print("  COEFICIENTES DE IMPACTO — NBR 7188:2013")
        print(sep)
        print(f"  Tipo estrutural : {r['tipo_estrutural']}")
        print(f"  Material        : {r['material']}")
        print(f"  Classe da via   : {r['classe_via']}")
        print(f"  CNF (constante) : {r['CNF']:.3f}")
        print(f"  Juntas em x [m] : {[f'{j:.2f}' for j in r['juntas_x_m']]}")
        print(f"  φ mínimo        : {r['phi_min']:.3f}")
        print(f"  φ máximo        : {r['phi_max']:.3f}")
        print()
        for nome, zonas in (
            ("CIA",     r["zonas_cia"]),
            ("CIV",     r["zonas_civ"]),
            ("CNF",     r["zonas_cnf"]),
            ("Impacto", r["zonas_impacto"]),
        ):
            print(f"  Zonas de {nome}:")
            for (xi, xf), val in zonas.items():
                print(f"    [{xi:8.3f}, {xf:8.3f}] m  →  {nome} = {val:.3f}")
            print()
        print(sep)


    # ════════════════════════════════════════════════════════════════════════════════
    # NOVO MÉTODO: obter_relatorio_resumido() — Memorial de Cálculo dos Coeficientes de Impacto
    # ════════════════════════════════════════════════════════════════════════════════

    def obter_relatorio_resumido(self) -> Tuple[str, str]:
        """
        Gera memorial de cálculo completo dos coeficientes de impacto (CIA, CIV, CNF, φ)
        conforme NBR 7188:2013.

        Retorna
        -------
        Tuple[str, str]
            (texto_plano, html_formatado) — relatório passo a passo, detalhando:
            • Dados da estrutura e classe da via
            • Construção dos segmentos e vãos de inércia
            • Posições das juntas e zonas de influência do CIA
            • Cálculo de cada coeficiente por trecho
            • Fusão de intervalos consecutivos
            • Tabela-resumo final
        """
        # ─────────────────────────────────────────────────────────────────────────
        # COLETA DE DADOS PARA O RELATÓRIO
        # ─────────────────────────────────────────────────────────────────────────
        tipo_estrutural = self._tipo
        material = self.material
        classe_via = self.sec.classe
        vaos = self._vaos
        laje = self._laje

        # Segmentos construídos (coordenadas reais)
        segmentos = self._segmentos
        juntas = self._juntas

        # Resultados das zonas
        zonas_cia = self.zonas_cia
        zonas_civ = self.zonas_civ
        zonas_cnf = self.zonas_cnf
        zonas_impacto = self.zonas_impacto

        cnf_constante = self._cnf()

        # Resumo geral
        resumo = self.resumo()
        phi_min = resumo['phi_min']
        phi_max = resumo['phi_max']

        # ─────────────────────────────────────────────────────────────────────────
        # RELATÓRIO EM TEXTO PLANO (ASCII art detalhada)
        # ─────────────────────────────────────────────────────────────────────────
        SEP_D = "=" * 80
        SEP_S = "-" * 80
        SEP_M = "-" * 60

        txt = []
        txt.append(SEP_D)
        txt.append("MEMORIAL DE CÁLCULO – COEFICIENTES DE IMPACTO")
        txt.append("Conforme NBR 7188:2013 – Carga móvel rodoviária e de pedestres")
        txt.append("CIA · CIV · CNF · φ (Impacto Total)")
        txt.append(SEP_D)

        # SEÇÃO 1 – DADOS DE ENTRADA
        txt.append("")
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 1 – DADOS DE ENTRADA                                │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append(f"  Tipo estrutural                : {tipo_estrutural}")
        txt.append(f"  Material                       : {material}")
        txt.append(f"  Classe da via (NBR 7188)        : {classe_via}")
        txt.append("")
        txt.append("  Vãos [m]: " + ", ".join([f"{v:.2f}" for v in vaos]))
        if laje:
            txt.append(f"  Laje de transição              : {laje:.2f} m (cada extremidade)")
        else:
            txt.append("  Laje de transição              : Não")
        txt.append("")

        # SEÇÃO 2 – CONSTRUÇÃO DOS SEGMENTOS ESTRUTURAIS
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 2 – SEGMENTOS ESTRUTURAIS E VÃOS DE INÉRCIA (Liv) │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  A estrutura é discretizada em trechos com propriedades uniformes.")
        txt.append("  Para cada segmento, calcula-se o vão de inércia Liv (NBR 7188 §5.1.2.1):")
        txt.append("    • Vão isostático              → Liv = comprimento do vão")
        txt.append("    • Vão contínuo                → Liv = média dos vãos do tramo contínuo")
        txt.append("    • Balanço                     → Liv = comprimento do balanço")
        txt.append("    • Laje de transição           → Liv = comprimento da laje")
        txt.append("")
        txt.append("  Segmentos (coordenadas reais x [m]):")
        txt.append(f"  {'Tipo':<15} {'x_ini [m]':>10} {'x_fim [m]':>10} {'Comp. [m]':>10} {'Liv [m]':>10}")
        txt.append("  " + "-" * 60)
        for seg in segmentos:
            txt.append(f"  {seg.tipo:<15} {seg.x_ini:>10.2f} {seg.x_fim:>10.2f} {seg.comprimento:>10.2f} {seg.liv:>10.2f}")
        txt.append("")

        # SEÇÃO 3 – JUNTAS DE DILATAÇÃO E ZONAS DE INFLUÊNCIA DO CIA
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 3 – JUNTAS DE DILATAÇÃO E ZONAS DE INFLUÊNCIA CIA  │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Conforme NBR 7188:2013 §5.1.2.3, o Coeficiente de Impacto Adicional (CIA)")
        txt.append("  assume valor majorado nos trechos situados a menos de 5,0 m de uma junta")
        txt.append("  de dilatação.")
        txt.append("")
        txt.append("  Posições das juntas identificadas (coordenada x [m]):")
        txt.append("    " + ", ".join([f"{j:.2f}" for j in juntas]))
        txt.append("")
        txt.append("  Valores de CIA adotados:")
        if material == "concreto_mista":
            txt.append(f"    • Fora da zona de influência : CIA = {CIA_NORMAL:.2f}")
            txt.append(f"    • Dentro de 5 m da junta     : CIA = {CIA_CONCRETO_MISTA:.2f} (concreto/mista)")
        else:
            txt.append(f"    • Fora da zona de influência : CIA = {CIA_NORMAL:.2f}")
            txt.append(f"    • Dentro de 5 m da junta     : CIA = {CIA_ACO:.2f} (aço)")
        txt.append("")

        # SEÇÃO 4 – CÁLCULO DOS COEFICIENTES POR TRECHO (ANTES DA FUSÃO)
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 4 – CÁLCULO DOS COEFICIENTES (POR SUB‑INTERVALO)   │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Para cada segmento, subdivide-se nos pontos de mudança do CIA")
        txt.append("  (junta ± 5,0 m). Em cada sub‑intervalo, calcula-se:")
        txt.append("    • CIV = f(Liv)  → 1,35 se Liv < 10 m; 1+1,06·(20/(Liv+50)) se 10≤Liv≤200")
        txt.append("    • CNF = constante em toda a estrutura")
        txt.append("    • CIA = conforme distância à junta mais próxima")
        txt.append("    • φ   = CIA · CIV · CNF")
        txt.append("")
        txt.append("  Sub‑intervalos brutos (antes da fusão de valores iguais consecutivos):")
        txt.append(f"  {'x_ini [m]':>10} {'x_fim [m]':>10} {'CIA':>6} {'CIV':>6} {'CNF':>6} {'φ':>7}")
        txt.append("  " + "-" * 52)

        # Para obter os intervalos brutos, podemos percorrer os segmentos e breakpoints novamente
        # (mesma lógica de _calcular_zonas, mas sem o merge).
        for seg in segmentos:
            civ = self._civ_de_liv(seg.liv)
            bps = {seg.x_ini, seg.x_fim}
            for j in self._juntas:
                for delta in (-LIMIAR_CIA_M, +LIMIAR_CIA_M):
                    bp = j + delta
                    if seg.x_ini < bp < seg.x_fim:
                        bps.add(bp)
            for xi, xf in zip(sorted(bps), sorted(bps)[1:]):
                if xf - xi < 1e-9:
                    continue
                cia = self._cia_em_ponto((xi + xf) / 2.0)
                phi = cia * civ * cnf_constante
                txt.append(f"  {xi:>10.2f} {xf:>10.2f} {cia:>6.2f} {civ:>6.2f} {cnf_constante:>6.2f} {phi:>7.3f}")
        txt.append("")

        # SEÇÃO 5 – FUSÃO DE ZONAS CONSECUTIVAS DE MESMO VALOR
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 5 – FUSÃO DE ZONAS CONSECUTIVAS (VALORES IGUAIS)   │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append("  Para simplificar a aplicação em projeto, intervalos adjacentes")
        txt.append("  com o mesmo valor (após arredondamento para 3 casas decimais) são")
        txt.append("  fundidos em um único trecho.")
        txt.append("")

        # SEÇÃO 6 – ZONAS FINAIS DE CADA COEFICIENTE
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 6 – ZONAS FINAIS DOS COEFICIENTES                  │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")

        def imprimir_zonas(txt_list, nome, zonas_dict):
            txt_list.append(f"  Zonas de {nome}:")
            if not zonas_dict:
                txt_list.append("    (nenhuma)")
            else:
                for (xi, xf), val in zonas_dict.items():
                    txt_list.append(f"    [{xi:>8.3f}, {xf:>8.3f}] m  →  {nome} = {val:.3f}")
            txt_list.append("")

        imprimir_zonas(txt, "CIA", zonas_cia)
        imprimir_zonas(txt, "CIV", zonas_civ)
        imprimir_zonas(txt, "CNF", zonas_cnf)
        imprimir_zonas(txt, "Impacto φ", zonas_impacto)

        # SEÇÃO 7 – SÍNTESE FINAL
        txt.append(SEP_S)
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 7 – SÍNTESE FINAL                                  │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append(f"  CNF (constante em toda a estrutura) = {cnf_constante:.3f}")
        txt.append(f"  φ mínimo  = {phi_min:.3f}")
        txt.append(f"  φ máximo  = {phi_max:.3f}")
        txt.append("")
        txt.append(SEP_D)
        txt.append("FIM DO MEMORIAL DE CÁLCULO")
        txt.append(SEP_D)

        texto_plano = "\n".join(txt)

        # ─────────────────────────────────────────────────────────────────────────
        # RELATÓRIO EM HTML (TEMA ESCURO PROFISSIONAL)
        # ─────────────────────────────────────────────────────────────────────────
        # Tabela de segmentos
        rows_seg = ""
        for seg in segmentos:
            rows_seg += (f"<tr><td>{seg.tipo}</td><td>{seg.x_ini:.2f}</td><td>{seg.x_fim:.2f}</td>"
                        f"<td>{seg.comprimento:.2f}</td><td>{seg.liv:.2f}</td></tr>")

        # Tabela de sub‑intervalos brutos
        rows_sub = ""
        for seg in segmentos:
            civ = self._civ_de_liv(seg.liv)
            bps = {seg.x_ini, seg.x_fim}
            for j in self._juntas:
                for delta in (-LIMIAR_CIA_M, +LIMIAR_CIA_M):
                    bp = j + delta
                    if seg.x_ini < bp < seg.x_fim:
                        bps.add(bp)
            for xi, xf in zip(sorted(bps), sorted(bps)[1:]):
                if xf - xi < 1e-9:
                    continue
                cia = self._cia_em_ponto((xi + xf) / 2.0)
                phi = cia * civ * cnf_constante
                rows_sub += (f"<tr><td>{xi:.2f}</td><td>{xf:.2f}</td><td>{cia:.2f}</td>"
                            f"<td>{civ:.2f}</td><td>{cnf_constante:.2f}</td><td>{phi:.3f}</td></tr>")

        # Tabelas de zonas finais
        def zonas_para_linhas(zonas_dict):
            linhas = ""
            for (xi, xf), val in sorted(zonas_dict.items()):
                linhas += f"<tr><td>[{xi:.3f}, {xf:.3f}]</td><td>{val:.3f}</td></tr>"
            return linhas

        rows_cia = zonas_para_linhas(zonas_cia)
        rows_civ = zonas_para_linhas(zonas_civ)
        rows_cnf = zonas_para_linhas(zonas_cnf)
        rows_phi = zonas_para_linhas(zonas_impacto)

        html = f"""<!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #0f172a; color: #e2e8f0; padding: 20px; font-size: 14px; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
        .header {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #1a237e 100%); padding: 28px; text-align: center; color: white; }}
        .header h1 {{ margin: 0 0 6px 0; font-size: 1.55em; letter-spacing: 0.5px; }}
        .header p  {{ margin: 0; opacity: 0.8; font-size: 0.92em; }}
        .content {{ padding: 28px; }}
        .section {{ margin-bottom: 28px; border-left: 4px solid #3b82f6; padding: 18px 18px 18px 20px; background: rgba(30,40,60,0.5); border-radius: 0 10px 10px 0; }}
        .section-title {{ font-size: 1.15em; font-weight: bold; color: #93c5fd; margin-bottom: 14px; border-bottom: 1px solid #334155; padding-bottom: 8px; }}
        .sub-title {{ color: #7dd3fc; font-weight: bold; margin: 18px 0 8px 0; font-size: 0.98em; }}
        .info-box {{ background: rgba(15,23,42,0.6); border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; border-left: 3px solid #6366f1; }}
        .formula-eq {{ background: #0f172a; border-left: 3px solid #f59e0b; padding: 10px 14px; font-family: 'Courier New', monospace; color: #fef3c7; font-size: 0.93em; margin: 8px 0; border-radius: 0 6px 6px 0; }}
        .resultado-destaque {{ background: #1e3a5f; border: 1px solid #3b82f6; border-radius: 6px; padding: 8px 14px; font-size: 1.08em; font-weight: bold; color: #93c5fd; margin: 10px 0; display: inline-block; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 0.88em; }}
        th {{ background: #1e3a5f; color: #93c5fd; padding: 7px 10px; text-align: center; border-bottom: 2px solid #3b82f6; }}
        td {{ padding: 6px 10px; border-bottom: 1px solid #1e293b; text-align: center; }}
        tr:hover td {{ background: rgba(59,130,246,0.08); }}
        td:first-child {{ text-align: left; color: #94a3b8; }}
        .footer {{ background: #0f172a; padding: 14px; text-align: center; color: #475569; font-size: 0.82em; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
            <h1>⚙️ Memorial de Cálculo – Coeficientes de Impacto</h1>
            <p>NBR 7188:2013 · CIA · CIV · CNF · φ (Impacto Total)</p>
        </div>
        <div class="content">

            <!-- SEÇÃO 1 – DADOS DE ENTRADA -->
            <div class="section">
                <div class="section-title">📌 SEÇÃO 1 – DADOS DE ENTRADA</div>
                <div class="grid-2">
                    <div>
                        <p class="sub-title">Estrutura</p>
                        <table>
                            <tr><td>Tipo estrutural</td><td><strong>{tipo_estrutural}</strong></td></tr>
                            <tr><td>Material</td><td><strong>{material}</strong></td></tr>
                            <tr><td>Classe da via</td><td><strong>{classe_via}</strong></td></tr>
                        </table>
                    </div>
                    <div>
                        <p class="sub-title">Geometria</p>
                        <table>
                            <tr><td>Vãos [m]</td><td><strong>{', '.join([f'{v:.2f}' for v in vaos])}</strong></td></tr>
                            <tr><td>Laje de transição</td><td><strong>{f'{laje:.2f} m' if laje else 'Não'}</strong></td></tr>
                        </table>
                    </div>
                </div>
            </div>

            <!-- SEÇÃO 2 – SEGMENTOS ESTRUTURAIS E VÃOS DE INÉRCIA -->
            <div class="section">
                <div class="section-title">📐 SEÇÃO 2 – SEGMENTOS ESTRUTURAIS E VÃOS DE INÉRCIA (Liv)</div>
                <p>Segmentos discretizados (coordenadas reais x [m]):</p>
                <table>
                    <thead><tr><th>Tipo</th><th>x_ini [m]</th><th>x_fim [m]</th><th>Comprimento [m]</th><th>Liv [m]</th></tr></thead>
                    <tbody>{rows_seg}</tbody>
                </table>
                <div class="info-box" style="margin-top:12px;">
                    <p><strong>Vão de inércia Liv (NBR 7188 §5.1.2.1):</strong><br>
                    • Isostático → comprimento do vão<br>
                    • Contínuo → média dos vãos do tramo<br>
                    • Balanço → comprimento do balanço<br>
                    • Laje → comprimento da laje</p>
                </div>
            </div>

            <!-- SEÇÃO 3 – JUNTAS E ZONAS DE INFLUÊNCIA CIA -->
            <div class="section">
                <div class="section-title">🚧 SEÇÃO 3 – JUNTAS DE DILATAÇÃO E ZONAS DE INFLUÊNCIA CIA</div>
                <p>Juntas identificadas em x [m]: <strong>{', '.join([f'{j:.2f}' for j in juntas])}</strong></p>
                <p>Valores de CIA (NBR 7188 §5.1.2.3):</p>
                <ul style="margin-left:20px; color:#cbd5e1;">
                    <li>Fora da zona de influência (≥ 5,0 m da junta): CIA = {CIA_NORMAL:.2f}</li>
                    <li>Dentro de 5,0 m da junta: CIA = {CIA_CONCRETO_MISTA if material=='concreto_mista' else CIA_ACO:.2f} ({material})</li>
                </ul>
            </div>

            <!-- SEÇÃO 4 – CÁLCULO POR SUB‑INTERVALO (BRUTO) -->
            <div class="section">
                <div class="section-title">🔢 SEÇÃO 4 – CÁLCULO DOS COEFICIENTES (POR SUB‑INTERVALO)</div>
                <p>Sub‑intervalos gerados a partir dos breakpoints (junta ± 5,0 m).</p>
                <table>
                    <thead><tr><th>x_ini [m]</th><th>x_fim [m]</th><th>CIA</th><th>CIV</th><th>CNF</th><th>φ</th></tr></thead>
                    <tbody>{rows_sub}</tbody>
                </table>
                <p class="formula-eq">CIV = 1,35 (Liv < 10 m)  ou  1 + 1,06·[20/(Liv+50)]  (10 ≤ Liv ≤ 200 m)</p>
            </div>

            <!-- SEÇÃO 5 – FUSÃO DE ZONAS -->
            <div class="section">
                <div class="section-title">🔄 SEÇÃO 5 – FUSÃO DE ZONAS CONSECUTIVAS</div>
                <p>Intervalos adjacentes com mesmo valor (arredondado para 3 casas decimais) são fundidos para simplificação.</p>
            </div>

            <!-- SEÇÃO 6 – ZONAS FINAIS -->
            <div class="section">
                <div class="section-title">📊 SEÇÃO 6 – ZONAS FINAIS DOS COEFICIENTES</div>
                <div class="grid-2">
                    <div>
                        <p class="sub-title">CIA</p>
                        <table><thead><tr><th>Intervalo [m]</th><th>CIA</th></tr></thead><tbody>{rows_cia}</tbody></table>
                    </div>
                    <div>
                        <p class="sub-title">CIV</p>
                        <table><thead><tr><th>Intervalo [m]</th><th>CIV</th></tr></thead><tbody>{rows_civ}</tbody></table>
                    </div>
                </div>
                <div style="margin-top:16px;">
                    <p class="sub-title">CNF (constante)</p>
                    <table style="width:auto;"><tr><td>CNF</td><td><strong>{cnf_constante:.3f}</strong></td></tr></table>
                </div>
                <div style="margin-top:16px;">
                    <p class="sub-title">Impacto Total φ = CIA · CIV · CNF</p>
                    <table><thead><tr><th>Intervalo [m]</th><th>φ</th></tr></thead><tbody>{rows_phi}</tbody></table>
                </div>
            </div>

            <!-- SEÇÃO 7 – SÍNTESE FINAL -->
            <div class="section">
                <div class="section-title">📋 SEÇÃO 7 – SÍNTESE FINAL</div>
                <div class="resultado-destaque" style="display:block;">
                    CNF (constante) = {cnf_constante:.3f}<br>
                    φ mínimo = {phi_min:.3f} &nbsp; | &nbsp; φ máximo = {phi_max:.3f}
                </div>
            </div>

        </div>
        <div class="footer">
            Memorial de Cálculo gerado automaticamente · Coeficientes de Impacto · NBR 7188:2013
        </div>
    </div>
    </body>
    </html>"""

        return texto_plano, html