"""
Calculadora_Flexao_Simples.py
==============================
Módulo completo de integração para dimensionamento de LONGARINAS à flexão simples.

Responsabilidades:
    1. Traduzir dados da UI (SecaoTransversalSuperestrutura) em ParametrosGeometricos
    2. Executar o dimensionamento via motor de cálculo rigoroso (NBR 6118:2014)
    3. Gerar desenhos técnicos com visualização de zona comprimida
    4. Validar e relatar adequadamente os resultados

Tipos de seção suportados (6 variações):
    ┌─────────────────────────────────────────────────────────────┐
    │ Seção Transversal     │ Com Laje Colaborante                │
    ├──────────────────────┼─────────────────────────────────────┤
    │ • Retangular         │ • Retangular + Laje (= Seção T)     │
    │ • T                  │ • T + Laje (T modificada)           │
    │ • I                  │ • I + Laje (I com mesa superior)    │
    └─────────────────────────────────────────────────────────────┘

Convenções de unidades:
    • Comprimentos  : centímetros [cm]
    • Momentos      : quilonewtons·metro [kN·m]
    • Resistências  : megapascal [MPa]
    • Áreas         : centímetro quadrado [cm²]

Convenções de sinal de momento:
    • Msd > 0  (POSITIVO)  → Sagging:  compressão no TOPO,    tração na BASE
    • Msd < 0  (NEGATIVO)  → Hogging:  compressão na BASE,    tração no TOPO

Referências normativas:
    • NBR 6118:2014 — Projeto de Estruturas de Concreto Armado (itens 14.6.4, 17.2.2, 17.3.5)
    • Pinheiro, L. M. — Fundamentos do Concreto Armado (Cap. 7)

Autor: Software de Projeto de Pontes
Data: 2025
"""

from __future__ import annotations

import math
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path
from matplotlib.patches import FancyBboxPatch
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

# ════════════════════════════════════════════════════════════════════════════════
# IMPORTAÇÕES DO MOTOR DE CÁLCULO
# ════════════════════════════════════════════════════════════════════════════════
try:
    from modules.dimensionamento_flexao import (
        ParametrosGeometricos,
        Retangulo,
        ResultadoDimensionamento,
        ClasseDuctilidade,
        dimensionar_flexao_simples,
        imprimir_resultado,
    )
except ImportError as e:
    raise ImportError(
        "Erro ao importar módulo de dimensionamento. "
        "Certifique-se de que 'dimensionamento_flexao.py' está no path.\n"
        f"Detalhe: {e}"
    )

try:
    from modules.funcoes_sec_super import calcular_secao, gerar_poligono_secao
except ImportError as e:
    raise ImportError(
        "Erro ao importar funções auxiliares. "
        "Certifique-se de que 'funcoes_sec_super.py' está no path.\n"
        f"Detalhe: {e}"
    )


# ════════════════════════════════════════════════════════════════════════════════
# 1. ENUMERAÇÕES E TIPOS
# ════════════════════════════════════════════════════════════════════════════════

class TipoSecao(Enum):
    """Enumeração dos tipos de seção transversal suportados."""
    RETANGULAR = "Retangular"
    T = "T"
    I = "I"


class SinalMomento(Enum):
    """Enumeração para identificar o sinal do momento solicitante."""
    POSITIVO = "positivo"
    NEGATIVO = "negativo"


# ════════════════════════════════════════════════════════════════════════════════
# 2. CLASSE CALCULADORA PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════════

class CalculadoraFlexaoSimples:
    """
    Classe gerenciadora do dimensionamento à flexão simples para longarinas.

    Funcionalidades principais:
        • Tradução de dados UI → modelo de cálculo
        • Suporte a 6 variações de seção (3 tipos × 2 com/sem laje)
        • Dimensionamento conforme NBR 6118:2014
        • Verificação de ductilidade (kx ≤ kx_lim)
        • Cálculo de armadura dupla (se necessário)
        • Verificação de área mínima

    Atributos de classe:
        TIPOS_SUPORTADOS: Lista dos tipos de seção aceitos
        DUCTILIDADE_PADRAO: Classe de ductilidade padrão para pontes
    """

    TIPOS_SUPORTADOS = [TipoSecao.RETANGULAR, TipoSecao.T, TipoSecao.I]
    DUCTILIDADE_PADRAO = ClasseDuctilidade.NORMAL  # Recomendado: ESPECIAL para pontes

    def __init__(self, ductilidade: ClasseDuctilidade = ClasseDuctilidade.NORMAL):
        """
        Inicializa a calculadora.

        Args:
            ductilidade: Classe de ductilidade conforme NBR 6118:2014.
                        Recomendado usar ESPECIAL (kx_lim = 0,35) para pontes.
        """
        self.ductilidade = ductilidade
        self.ultimo_resultado: Optional[ResultadoDimensionamento] = None
        self.ultima_geometria: Optional[ParametrosGeometricos] = None

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODOS DE TRADUÇÃO: dados UI → ParametrosGeometricos
    # ─────────────────────────────────────────────────────────────────────────

    def _criar_secao_retangular(
        self,
        bw: float,
        h: float,
        d_pos: float,
        d_neg: float,
        fck: float,
        fyk: float,
    ) -> ParametrosGeometricos:
        """
        Cria objeto ParametrosGeometricos para seção retangular simples.

        Args:
            bw: largura da seção [cm]
            h: altura total da seção [cm]
            d_pos: altura útil para momento positivo [cm]
            d_neg: altura útil para momento negativo [cm]
            fck: resistência característica do concreto [MPa]
            fyk: resistência característica do aço [MPa]

        Returns:
            ParametrosGeometricos configurado para seção retangular
        """
        retangulos = [
            Retangulo(b=bw, h=h, y_base=0.0, nome="alma")
        ]
        return ParametrosGeometricos(
            retangulos=retangulos,
            d_pos=d_pos,
            d_neg=d_neg,
            fck=fck,
            fyk=fyk,
            ductilidade=self.ductilidade,
        )

    def _criar_secao_T(
        self,
        bw: float,
        h: float,
        bf: float,
        hf: float,
        d_pos: float,
        d_neg: float,
        fck: float,
        fyk: float,
    ) -> ParametrosGeometricos:
        """
        Cria objeto ParametrosGeometricos para seção T.

        A seção T é composta por dois retângulos:
            1. Alma (web): bw × (h - hf), na base
            2. Mesa (flange): bf × hf, no topo

        Args:
            bw: largura da alma [cm]
            h: altura total da seção (alma + mesa) [cm]
            bf: largura da mesa [cm]
            hf: altura da mesa [cm]
            d_pos: altura útil para momento positivo [cm]
            d_neg: altura útil para momento negativo [cm]
            fck: resistência característica do concreto [MPa]
            fyk: resistência característica do aço [MPa]

        Returns:
            ParametrosGeometricos configurado para seção T
        """
        h_alma = h - hf
        retangulos = [
            Retangulo(b=bw, h=h_alma, y_base=0.0, nome="alma"),
            Retangulo(b=bf, h=hf, y_base=h_alma, nome="mesa_superior"),
        ]
        return ParametrosGeometricos(
            retangulos=retangulos,
            d_pos=d_pos,
            d_neg=d_neg,
            fck=fck,
            fyk=fyk,
            ductilidade=self.ductilidade,
        )

    def _criar_secao_I(
        self,
        bw: float,
        h: float,
        btf: float,
        hft: float,
        bfb: float,
        hfb: float,
        d_pos: float,
        d_neg: float,
        fck: float,
        fyk: float,
    ) -> ParametrosGeometricos:
        """
        Cria objeto ParametrosGeometricos para seção I (dupla simetria).

        A seção I é composta por três retângulos:
            1. Mesa inferior: bfb × hfb
            2. Alma (web):     bw × (h - hft - hfb)
            3. Mesa superior:  btf × hft

        Args:
            bw: largura da alma [cm]
            h: altura total da seção [cm]
            btf: largura da mesa superior [cm]
            hft: altura da mesa superior [cm]
            bfb: largura da mesa inferior [cm]
            hfb: altura da mesa inferior [cm]
            d_pos: altura útil para momento positivo [cm]
            d_neg: altura útil para momento negativo [cm]
            fck: resistência característica do concreto [MPa]
            fyk: resistência característica do aço [MPa]

        Returns:
            ParametrosGeometricos configurado para seção I
        """
        h_alma = h - hft - hfb
        retangulos = [
            Retangulo(b=bfb, h=hfb, y_base=0.0, nome="mesa_inferior"),
            Retangulo(b=bw, h=h_alma, y_base=hfb, nome="alma"),
            Retangulo(b=btf, h=hft, y_base=(hfb + h_alma), nome="mesa_superior"),
        ]
        return ParametrosGeometricos(
            retangulos=retangulos,
            d_pos=d_pos,
            d_neg=d_neg,
            fck=fck,
            fyk=fyk,
            ductilidade=self.ductilidade,
        )

    def _criar_secao_com_laje(
        self,
        geo_base: ParametrosGeometricos,
        h_laje: float,
        b_laje: float,
    ) -> ParametrosGeometricos:
        """
        Estende uma seção existente adicionando a laje colaborante no topo.

        Args:
            geo_base: Geometria da longarina (sem laje)
            h_laje: altura da laje colaborante [cm]
            b_laje: largura colaborante da laje [cm]

        Returns:
            Nova ParametrosGeometricos com laje incorporada
        """
        h_total_base = geo_base.h_total
        retangulos_novos = list(geo_base.retangulos)
        retangulos_novos.append(
            Retangulo(
                b=b_laje,
                h=h_laje,
                y_base=h_total_base,
                nome="laje_colaborante"
            )
        )
        
        # Cria nova geometria com laje
        return ParametrosGeometricos(
            retangulos=retangulos_novos,
            d_pos=geo_base.d_pos,
            d_neg=geo_base.d_neg,
            fck=geo_base.fck,
            fyk=geo_base.fyk,
            gamma_c=geo_base.gamma_c,
            gamma_s=geo_base.gamma_s,
            ductilidade=geo_base.ductilidade,
        )

    def _traduzir_dados_ui(
        self,
        dados: Dict,
        d_pos: float,
        d_neg: float,
        fck: float,
        fyk: float,
        h_laje: Optional[float] = None,
        b_laje: Optional[float] = None,
    ) -> ParametrosGeometricos:
        """
        Traduz dicionário de dados da UI em objeto ParametrosGeometricos.

        Args:
            dados: Dicionário com chaves "Tipo", "bw", "h" e parâmetros adicionais
            d_pos: altura útil para momento positivo [cm]
            d_neg: altura útil para momento negativo [cm]
            fck: resistência do concreto [MPa]
            fyk: resistência do aço [MPa]
            h_laje: espessura da laje colaborante [cm], se existir
            b_laje: largura colaborante da laje [cm], se existir

        Returns:
            ParametrosGeometricos montado e validado

        Raises:
            ValueError: Se tipo de seção inválido ou dados inconsistentes
        """
        tipo = dados.get("Tipo")
        if not tipo:
            raise ValueError("Chave 'Tipo' obrigatória no dicionário de dados.")

        # Cria a geometria base conforme o tipo
        if tipo == TipoSecao.RETANGULAR.value or tipo == "Retangular":
            bw = dados.get("bw")
            h = dados.get("h")
            if not bw or not h:
                raise ValueError(f"Seção Retangular: parâmetros 'bw' e 'h' obrigatórios.")
            geo = self._criar_secao_retangular(
                bw=bw, h=h, d_pos=d_pos, d_neg=d_neg, fck=fck, fyk=fyk
            )

        elif tipo == TipoSecao.T.value or tipo == "T":
            bw = dados.get("bw")
            h = dados.get("h")
            bf = dados.get("bf")
            hf = dados.get("hf")
            if not all([bw, h, bf, hf]):
                raise ValueError(
                    f"Seção T: parâmetros 'bw', 'h', 'bf', 'hf' obrigatórios."
                )
            geo = self._criar_secao_T(
                bw=bw, h=h, bf=bf, hf=hf,
                d_pos=d_pos, d_neg=d_neg, fck=fck, fyk=fyk
            )

        elif tipo == TipoSecao.I.value or tipo == "I":
            bw = dados.get("bw")
            h = dados.get("h")
            btf = dados.get("btf")
            hft = dados.get("hft")
            bfb = dados.get("bfb")
            hfb = dados.get("hfb")
            if not all([bw, h, btf, hft, bfb, hfb]):
                raise ValueError(
                    f"Seção I: parâmetros 'bw', 'h', 'btf', 'hft', 'bfb', 'hfb' obrigatórios."
                )
            geo = self._criar_secao_I(
                bw=bw, h=h, btf=btf, hft=hft, bfb=bfb, hfb=hfb,
                d_pos=d_pos, d_neg=d_neg, fck=fck, fyk=fyk
            )

        else:
            raise ValueError(
                f"Tipo de seção '{tipo}' não suportado. "
                f"Tipos válidos: {[t.value for t in TipoSecao]}"
            )

        # Adiciona laje colaborante se fornecida
        tem_laje = h_laje is not None and b_laje is not None
        if tem_laje:
            if h_laje <= 0 or b_laje <= 0:
                raise ValueError("Laje: h_laje e b_laje devem ser > 0.")
            geo = self._criar_secao_com_laje(geo, h_laje=h_laje, b_laje=b_laje)

        return geo

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODO PRINCIPAL DE DIMENSIONAMENTO
    # ─────────────────────────────────────────────────────────────────────────

    def dimensionar(
        self,
        dados: Dict,
        Msd: float,
        d_pos: float,
        d_neg: float,
        fck: float = 30.0,
        fyk: float = 500.0,
        h_laje: Optional[float] = None,
        b_laje: Optional[float] = None,
        d_linha_armadura: float = 5.0,
        calcular_armadura_dupla: bool = True,
    ) -> ResultadoDimensionamento:
        """
        Executa o dimensionamento à flexão simples completo.

        Fluxo:
            1. Valida entradas
            2. Monta geometria (ParametrosGeometricos)
            3. Executa cálculo rigoroso (NBR 6118:2014)
            4. Retorna resultado detalhado

        Args:
            dados: Dicionário com "Tipo", "bw", "h" e parâmetros específicos
            Msd: Momento de cálculo [kN·m]
                 > 0 → Sagging (compressão no topo)
                 < 0 → Hogging (compressão na base)
            d_pos: Altura útil para momento positivo [cm]
                   (distância do topo à armadura de tração inferior)
            d_neg: Altura útil para momento negativo [cm]
                   (distância da base à armadura de tração superior)
            fck: Resistência característica do concreto [MPa]. Default: 30
            fyk: Resistência característica do aço [MPa]. Default: 500
            h_laje: Altura da laje colaborante [cm], opcional
            b_laje: Largura colaborante [cm], opcional
            d_linha_armadura: Cobrimento da armadura de compressão [cm], para armadura dupla
            calcular_armadura_dupla: Se True, calcula A's quando necessário

        Returns:
            ResultadoDimensionamento com todos os campos preenchidos:
            - Msd, sinal_momento
            - d, fcd, fyd, kx_lim
            - a (profundidade bloco), x (linha neutra), kx, z, Fcc
            - As_calc, As_min, As_adotar
            - Flags: armadura_dupla_necessaria, secao_insuficiente
            - Alertas com recomendações

        Raises:
            ValueError: Se dados inválidos ou incompletos
        """
        # Validação básica
        if not dados:
            raise ValueError("Dicionário 'dados' vazio.")
        if not isinstance(Msd, (int, float)):
            raise ValueError(f"Msd deve ser numérico; recebido: {type(Msd)}")
        if d_pos <= 0 or d_neg <= 0:
            raise ValueError("Altura útil (d_pos, d_neg) deve ser > 0.")

        # Traduz dados da UI
        geo = self._traduzir_dados_ui(
            dados=dados,
            d_pos=d_pos,
            d_neg=d_neg,
            fck=fck,
            fyk=fyk,
            h_laje=h_laje,
            b_laje=b_laje,
        )

        # Executa dimensionamento rigoroso
        resultado = dimensionar_flexao_simples(
            geo=geo,
            Msd=Msd,
            d_linha_armadura=d_linha_armadura,
            calcular_armadura_dupla=calcular_armadura_dupla,
        )

        # Armazena para acesso posterior (ex.: para desenho)
        self.ultimo_resultado = resultado
        self.ultima_geometria = geo

        return resultado

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODOS AUXILIARES DE CONSULTA
    # ─────────────────────────────────────────────────────────────────────────

    def obter_ultimo_resultado(self) -> Optional[ResultadoDimensionamento]:
        """Retorna o último resultado calculado, ou None se nenhum cálculo foi feito."""
        return self.ultimo_resultado

    def obter_ultima_geometria(self) -> Optional[ParametrosGeometricos]:
        """Retorna a última geometria utilizada, ou None se nenhum cálculo foi feito."""
        return self.ultima_geometria

    def eh_secao_adequada(self) -> bool:
        """
        Verifica se a seção é adequada (sem flags de erro).

        Returns:
            True se a seção é adequada, False se insuficiente ou requer armadura dupla
        """
        if not self.ultimo_resultado:
            return False
        r = self.ultimo_resultado
        return (not r.secao_insuficiente) and (not r.armadura_dupla_necessaria)

    def obter_relatorio_resumido(self) -> Tuple[str, str]:
        """
        Gera memorial de cálculo completo, passo a passo, com fórmulas e verificações.
        
        Retorna uma tupla (texto_plano, html_formatado) contendo:
            - texto_plano: versão em texto puro com formatação simples
            - html_formatado: versão HTML com CSS para tema escuro e fórmulas

        Returns:
            Tuple[str, str]: (relatório_texto, relatório_html)
        """
        if not self.ultimo_resultado or not self.ultima_geometria:
            msg = "Nenhum dimensionamento realizado ainda."
            return msg, f"<p>{msg}</p>"

        r = self.ultimo_resultado
        g = self.ultima_geometria

        # Extrair dados básicos
        fck = g.fck
        fyk = g.fyk
        gamma_c = getattr(g, 'gamma_c', 1.4)
        gamma_s = getattr(g, 'gamma_s', 1.15)
        fcd = fck / gamma_c
        fyd = fyk / gamma_s

        # Coeficientes de conformidade NBR 6118 (concreto até C50)
        lamb = 0.8   # λ
        alpha_c = 0.85  # αc

        # Altura útil conforme sinal do momento
        d = r.d
        # Posição da linha neutra e profundidade do bloco
        x = r.x
        a = r.a
        kx = r.kx
        kx_lim = r.kx_lim
        z = r.z
        Fcc = r.Fcc
        Msd = r.Msd
        sinal = r.sinal_momento

        # Momentos e armadura
        As_calc = r.As_calc
        As_min = r.As_min
        As_adotar = r.As_adotar

        # Armadura dupla
        arm_dupla = r.armadura_dupla_necessaria
        if arm_dupla:
            As_linha = getattr(r, 'As_linha', 0.0)
            d_linha = getattr(r, 'd_linha', 0.0)
            As_adicional = getattr(r, 'As_adicional', 0.0)
            Mrd_lim = getattr(r, 'Mrd_lim', 0.0)
            delta_M = getattr(r, 'delta_M', 0.0)
        else:
            As_linha = As_adicional = Mrd_lim = delta_M = d_linha = 0.0

        # Verificações
        ductil_ok = (kx <= kx_lim)
        secao_ok = not r.secao_insuficiente
        alertas = r.alertas if r.alertas else []

        # Cálculo do centroide do bloco ξ_cg (posição medida da face comprimida)
        # Usaremos a definição: ξ_cg = d - z
        xi_cg = d - z

        # Cálculo detalhado de ρ_min (usado na armadura mínima)
        if fck <= 50.0:
            fctm = 0.3 * (fck ** (2.0/3.0))
        else:
            fctm = 2.12 * math.log(1.0 + fck/10.0)
        rho_min = max(0.26 * fctm / fyk, 0.0013)
        bw = g.bw

        # ─────────────────────────────────────────────────────────────────────
        # RELATÓRIO EM TEXTO PURO (passo a passo detalhado)
        # ─────────────────────────────────────────────────────────────────────
        texto = []
        texto.append("=" * 80)
        texto.append("MEMORIAL DE CÁLCULO – FLEXÃO SIMPLES (NBR 6118:2014)")
        texto.append("=" * 80)
        texto.append("")
        texto.append("1. DADOS DE ENTRADA")
        texto.append("-" * 40)
        texto.append(f"   Momento solicitante de cálculo (Msd)  = {Msd:8.2f} kN·m  ({sinal.upper()})")
        texto.append(f"   Resistência do concreto (fck)         = {fck:8.2f} MPa")
        texto.append(f"   Resistência do aço (fyk)              = {fyk:8.2f} MPa")
        texto.append(f"   Coeficiente de ponderação (γc)        = {gamma_c:.2f}")
        texto.append(f"   Coeficiente de ponderação (γs)        = {gamma_s:.2f}")
        texto.append("")
        texto.append("2. PROPRIEDADES DOS MATERIAIS")
        texto.append("-" * 40)
        texto.append(f"   Resistência de cálculo do concreto: fcd = fck / γc = {fck:.2f} / {gamma_c:.2f} = {fcd:.2f} MPa")
        texto.append(f"   Resistência de cálculo do aço:     fyd = fyk / γs = {fyk:.2f} / {gamma_s:.2f} = {fyd:.2f} MPa")
        texto.append(f"   Coeficientes para concreto até C50: λ = {lamb:.2f}  |  αc = {alpha_c:.2f}")
        texto.append("")
        texto.append("3. GEOMETRIA DA SEÇÃO TRANSVERSAL")
        texto.append("-" * 40)
        texto.append("   Componentes da seção (da base para o topo):")
        for i, rect in enumerate(g.retangulos, 1):
            texto.append(f"      {i}) {rect.nome}: largura = {rect.b:6.2f} cm, altura = {rect.h:6.2f} cm, y_base = {rect.y_base:6.2f} cm")
        texto.append(f"   Altura total (h_total)               = {g.h_total:8.2f} cm")
        texto.append(f"   Altura útil para {sinal} (d)        = {d:8.2f} cm")
        texto.append("")
        texto.append("4. CÁLCULO DA PROFUNDIDADE DO BLOCO DE COMPRESSÃO (a) POR BISSECÇÃO")
        texto.append("-" * 40)
        texto.append("   O equilíbrio de momentos exige que Mcc(a) = Msd, onde Mcc(a) é o momento")
        texto.append("   resistido pelo concreto em função da profundidade a do bloco retangular.")
        texto.append("   Como a relação é não linear, utiliza-se o método da bisseção:")
        texto.append("   • a_min = 0, a_max = d (limite físico).")
        texto.append("   • Calcula-se Mcc(a_mid) e reduz-se o intervalo até convergência.")
        texto.append(f"   Tolerância adotada: 1e-6 kN·m | Número máximo de iterações: 120")
        texto.append(f"   Valor encontrado para a: {a:.4f} cm")
        texto.append("")
        texto.append("5. CÁLCULO DA LINHA NEUTRA (x) E VERIFICAÇÃO DE DUCTILIDADE")
        texto.append("-" * 40)
        texto.append(f"   x = a / λ = {a:.4f} / {lamb:.2f} = {x:.4f} cm")
        texto.append(f"   kx = x / d = {x:.4f} / {d:.2f} = {kx:.4f}")
        texto.append(f"   kx_lim (ductilidade) = {kx_lim:.2f}")
        if ductil_ok:
            texto.append("   ✓ kx ≤ kx_lim → seção dúctil (atende NBR 6118).")
        else:
            texto.append("   ✗ kx > kx_lim → seção pouco dúctil, armadura dupla necessária.")
        texto.append("")
        texto.append("6. CÁLCULO DO CENTROIDE DO BLOCO DE COMPRESSÃO (ξ_cg)")
        texto.append("-" * 40)
        texto.append("   ξ_cg é a distância da face comprimida até a resultante Fcc, calculada por:")
        texto.append("   ξ_cg = (Σ dF_i · ξ_i) / Fcc, onde ξ_i é o centroide de cada fatia no sistema")
        texto.append("   de coordenadas ξ (origem na face comprimida).")
        texto.append(f"   Para esta seção, a integração resultou em ξ_cg = {xi_cg:.2f} cm.")
        texto.append("")
        texto.append("7. CÁLCULO DA RESULTANTE DE COMPRESSÃO (Fcc) E BRAÇO DE ALAVANCA (z)")
        texto.append("-" * 40)
        texto.append(f"   Fcc = {Fcc:.2f} kN")
        texto.append(f"   z = d - ξ_cg = {d:.2f} - {xi_cg:.2f} = {z:.2f} cm")
        momento_resistido = Fcc * z / 100.0
        texto.append(f"   Momento resistido pelo concreto: Mcc = Fcc·z/100 = {momento_resistido:.2f} kN·m")
        texto.append("")
        texto.append("8. VERIFICAÇÃO DA NECESSIDADE DE ARMADURA DUPLA")
        texto.append("-" * 40)
        if arm_dupla:
            texto.append(f"   → O momento solicitante excede o momento limite da seção com armadura simples.")
            texto.append(f"   Momento limite (Mrd,lim, com kx = kx_lim) = {Mrd_lim:.2f} kN·m")
            texto.append(f"   Excedente (ΔM = Msd - Mrd,lim) = {delta_M:.2f} kN·m")
            texto.append("   Será calculada armadura de compressão (A's) e adicional de tração.")
        else:
            texto.append(f"   → O momento solicitante é inferior ao momento resistido pelo concreto.")
            texto.append("   Não é necessária armadura de compressão.")
        texto.append("")
        texto.append("9. CÁLCULO DA ÁREA DE AÇO DE TRAÇÃO (As,calc)")
        texto.append("-" * 40)
        texto.append("   Equilíbrio de forças: As,base = Fcc / fyd   (com fyd em kN/cm²)")
        texto.append(f"   fyd = {fyd:.2f} MPa = {fyd*0.1:.2f} kN/cm²")
        texto.append(f"   As,base = {Fcc:.2f} / {fyd*0.1:.2f} = {Fcc/(fyd*0.1):8.2f} cm²")
        if arm_dupla and As_adicional > 0:
            texto.append(f"   Parcela adicional por armadura dupla: As,adicional = {As_adicional:8.2f} cm²")
            texto.append(f"   As,calc = As,base + As,adicional = {As_calc:8.2f} cm²")
        else:
            texto.append(f"   As,calc = As,base = {As_calc:8.2f} cm²")
        texto.append("")
        texto.append("10. CÁLCULO DA ÁREA MÍNIMA DE ARMADURA (As,min) – NBR 6118 Tabela 17.3")
        texto.append("-" * 40)
        texto.append(f"   ρ_mín = max(0,26·fctm/fyk, 0,0013)")
        texto.append(f"   fctm = {fctm:.2f} MPa  (para fck = {fck:.1f} MPa)")
        texto.append(f"   0,26·fctm/fyk = 0.26*{fctm:.2f}/{fyk:.1f} = {0.26*fctm/fyk:.6f}")
        texto.append(f"   ρ_mín = {rho_min:.6f}")
        texto.append(f"   bw (menor largura) = {bw:.2f} cm")
        texto.append(f"   As,min = ρ_mín · bw · d = {rho_min:.6f} · {bw:.2f} · {d:.2f} = {As_min:8.2f} cm²")
        texto.append("")
        texto.append("11. VERIFICAÇÃO FINAL E ARMADURA ADOTADA")
        texto.append("-" * 40)
        if As_calc >= As_min:
            texto.append(f"   As,calc ({As_calc:.2f}) ≥ As,min ({As_min:.2f}) → OK, adota-se As,calc")
        else:
            texto.append(f"   As,calc ({As_calc:.2f}) < As,min ({As_min:.2f}) → Adota-se As,min")
        texto.append(f"   Armadura de tração adotada (As,adot) = {As_adotar:8.2f} cm²")
        if arm_dupla:
            texto.append(f"   Armadura de compressão (A's) = {As_linha:8.2f} cm²  (cobrimento d' = {d_linha:.1f} cm)")
        texto.append("")
        texto.append("12. VERIFICAÇÕES NORMATIVAS FINAIS")
        texto.append("-" * 40)
        texto.append(f"   Seção suficiente (domínio 2 ou 3): {'✓ Sim' if secao_ok else '✗ Não'}")
        texto.append(f"   Ductilidade (kx ≤ kx_lim): {'✓ Atende' if ductil_ok else '✗ Não atende'}")
        if alertas:
            texto.append("   Alertas:")
            for al in alertas:
                texto.append(f"      ⚠ {al}")
        texto.append("")
        texto.append("=" * 80)
        texto.append("FIM DO MEMORIAL")
        texto_plano = "\n".join(texto)

        # ─────────────────────────────────────────────────────────────────────
        # RELATÓRIO EM HTML (tema escuro profissional)
        # ─────────────────────────────────────────────────────────────────────
        status_icon = "✅" if secao_ok and ductil_ok else "⚠️"
        status_color = "#2ecc71" if secao_ok and ductil_ok else "#e67e22"

        html_parts = []
        html_parts.append("""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background-color: #1e1e2f;
        margin: 0;
        padding: 20px;
        color: #e0e0e0;
    }
    .container {
        max-width: 1000px;
        margin: 0 auto;
        background: #2d2d3f;
        border-radius: 16px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.5);
        overflow: hidden;
        border: 1px solid #3a3a4f;
    }
    .header {
        background: linear-gradient(135deg, #0b2b3b, #1a4a6e);
        color: #ffffff;
        padding: 20px 30px;
        text-align: center;
        border-bottom: 1px solid #2c6e9e;
    }
    .header h1 {
        margin: 0;
        font-size: 1.8em;
        font-weight: 600;
    }
    .header p {
        margin: 5px 0 0;
        opacity: 0.85;
        font-size: 0.9em;
    }
    .content {
        padding: 25px 30px;
    }
    .section {
        margin-bottom: 30px;
        border-left: 4px solid #3498db;
        padding-left: 20px;
        background: rgba(30,30,47,0.5);
        border-radius: 0 12px 12px 0;
    }
    .section-title {
        font-size: 1.4em;
        font-weight: 600;
        color: #aad4ff;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        gap: 10px;
        border-bottom: 1px solid #3a3a4f;
        padding-bottom: 6px;
    }
    .formula {
        background: #1e1e2a;
        border-left: 3px solid #e67e22;
        padding: 10px 15px;
        margin: 12px 0;
        font-family: 'Courier New', monospace;
        font-size: 0.95em;
        overflow-x: auto;
        color: #f0f0f0;
        border-radius: 6px;
    }
    .value-table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
    }
    .value-table td {
        padding: 8px 12px;
        border-bottom: 1px solid #3a3a4f;
    }
    .value-table td:first-child {
        font-weight: 600;
        width: 45%;
        color: #bbbbdd;
    }
    .badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85em;
        font-weight: 600;
    }
    .badge-ok { background: #1e5a2e; color: #c8e6d9; border: 1px solid #2ecc71; }
    .badge-warning { background: #7e5a1a; color: #ffe5b4; border: 1px solid #f39c12; }
    .badge-danger { background: #8b2c2c; color: #ffcccc; border: 1px solid #e74c3c; }
    .alert {
        background: #3a2a1a;
        border-left: 4px solid #f39c12;
        padding: 12px 18px;
        margin: 15px 0;
        border-radius: 8px;
        color: #ffe0b3;
    }
    .footer {
        background: #1e1e2a;
        text-align: center;
        padding: 12px;
        font-size: 0.8em;
        color: #9aa0b0;
        border-top: 1px solid #3a3a4f;
    }
    hr {
        margin: 20px 0;
        border: 0;
        height: 1px;
        background: linear-gradient(to right, #3a3a4f, transparent);
    }
    strong {
        color: #ffd966;
    }
    a {
        color: #5dade2;
    }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📐 Memorial de Cálculo – Flexão Simples</h1>
        <p>Referência Normativa: NBR 6118:2023 – Projeto de estruturas de concreto</p>
    </div>
    <div class="content">
""")

        # 1. Dados de entrada
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">📌 1. DADOS DE ENTRADA</div>
            <table class="value-table">
                <tr><td>Momento solicitante de cálculo (Msd):</td><td><strong>{Msd:.2f} kN·m</strong> ({sinal.upper()})</td></tr>
                <tr><td>Resistência do concreto (fck):</td><td>{fck:.2f} MPa</td></tr>
                <tr><td>Resistência do aço (fyk):</td><td>{fyk:.2f} MPa</td></tr>
                <tr><td>Coeficientes de ponderação:</td><td>γc = {gamma_c:.2f} &nbsp;&nbsp; γs = {gamma_s:.2f}</td></tr>
            </table>
        </div>
""")

        # 2. Propriedades dos materiais
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">🧱 2. PROPRIEDADES DOS MATERIAIS</div>
            <div class="formula">f<sub>cd</sub> = f<sub>ck</sub> / γ<sub>c</sub> = {fck:.2f} / {gamma_c:.2f} = {fcd:.2f} MPa</div>
            <div class="formula">f<sub>yd</sub> = f<sub>yk</sub> / γ<sub>s</sub> = {fyk:.2f} / {gamma_s:.2f} = {fyd:.2f} MPa</div>
            <div class="formula">λ = {lamb:.2f} &nbsp;&nbsp; (para concreto ≤ C50)<br>α<sub>c</sub> = {alpha_c:.2f}</div>
        </div>
""")

        # 3. Geometria
        geom_html = "<div class='section'><div class='section-title'>📐 3. GEOMETRIA DA SEÇÃO</div><table class='value-table'>"
        for rect in g.retangulos:
            geom_html += f"<tr><td>{rect.nome.capitalize()}:</td><td>largura = {rect.b:.1f} cm, altura = {rect.h:.1f} cm, y_base = {rect.y_base:.1f} cm</td></tr>"
        geom_html += f"<tr><td>Altura total (h<sub>total</sub>):</td><td>{g.h_total:.2f} cm</td></tr>"
        geom_html += f"<tr><td>Altura útil para {sinal} (d):</td><td>{d:.2f} cm</td></tr></table></div>"
        html_parts.append(geom_html)

        # 4. Cálculo de a por bisseção
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">🔢 4. CÁLCULO DA PROFUNDIDADE DO BLOCO (a) POR BISSECÇÃO</div>
            <div class="formula">Equação de equilíbrio: M<sub>cc</sub>(a) = M<sub>sd</sub></div>
            <div class="formula">Método da bisseção: busca a raiz de f(a) = M<sub>cc</sub>(a) - M<sub>sd</sub> = 0</div>
            <div class="formula">Intervalo inicial: [0, d] = [0, {d:.2f}] cm</div>
            <div class="formula">Tolerância: 1e-6 kN·m | Máximo de iterações: 120</div>
            <div class="formula"><strong>a = {a:.4f} cm</strong> (profundidade do bloco retangular de tensões)</div>
        </div>
""")

        # 5. Linha neutra e ductilidade
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">📐 5. LINHA NEUTRA (x) E DUCTILIDADE</div>
            <div class="formula">x = a / λ = {a:.4f} / {lamb:.2f} = {x:.4f} cm</div>
            <div class="formula">k<sub>x</sub> = x / d = {x:.4f} / {d:.2f} = {kx:.4f}</div>
            <div class="formula">k<sub>x,lim</sub> = {kx_lim:.2f}</div>
            <div class="formula">{'✅ k<sub>x</sub> ≤ k<sub>x,lim</sub> → seção dúctil' if ductil_ok else '❌ k<sub>x</sub> > k<sub>x,lim</sub> → armadura dupla necessária'}</div>
        </div>
""")

        # 6. Centroide do bloco ξ_cg
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">🎯 6. CENTROIDE DO BLOCO DE COMPRESSÃO (ξ<sub>cg</sub>)</div>
            <div class="formula">ξ<sub>cg</sub> = (Σ dF<sub>i</sub> · ξ<sub>i</sub>) / F<sub>cc</sub></div>
            <div class="formula">ξ<sub>i</sub> é a coordenada medida da face comprimida até o centroide de cada fatia.</div>
            <div class="formula">Para esta seção, a integração resultou em <strong>ξ<sub>cg</sub> = {xi_cg:.2f} cm</strong>.</div>
        </div>
""")

        # 7. Fcc e z
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">⚖️ 7. RESULTANTE DE COMPRESSÃO (F<sub>cc</sub>) E BRAÇO DE ALAVANCA (z)</div>
            <div class="formula">F<sub>cc</sub> = {Fcc:.2f} kN</div>
            <div class="formula">z = d - ξ<sub>cg</sub> = {d:.2f} - {xi_cg:.2f} = {z:.2f} cm</div>
            <div class="formula">M<sub>cc</sub> = F<sub>cc</sub> · z / 100 = {Fcc:.2f} × {z:.2f} / 100 = {momento_resistido:.2f} kN·m</div>
        </div>
""")

        # 8. Armadura dupla
        if arm_dupla:
            html_parts.append(f"""
        <div class="section">
            <div class="section-title">🔄 8. ARMADURA DUPLA NECESSÁRIA</div>
            <div class="alert">⚠️ O momento solicitante excede o momento limite da seção com armadura simples.</div>
            <div class="formula">M<sub>Rd,lim</sub> (kx = kx_lim) = {Mrd_lim:.2f} kN·m</div>
            <div class="formula">ΔM = M<sub>Sd</sub> - M<sub>Rd,lim</sub> = {delta_M:.2f} kN·m</div>
            <div class="formula">A'<sub>s</sub> = ΔM / [f<sub>yd</sub> · (d - d')] = {As_linha:.2f} cm² &nbsp;(d' = {d_linha:.1f} cm)</div>
            <div class="formula">As<sub>adicional</sub> = A'<sub>s</sub> = {As_adicional:.2f} cm²</div>
        </div>
""")
        else:
            html_parts.append(f"""
        <div class="section">
            <div class="section-title">✅ 8. VERIFICAÇÃO DE ARMADURA DUPLA</div>
            <p>Momento solicitante ≤ momento resistido pelo concreto. <strong>Não há necessidade de armadura de compressão.</strong></p>
        </div>
""")

        # 9. Cálculo de As,calc
        base_as = Fcc/(fyd*0.1)
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">⚔️ 9. ÁREA DE AÇO DE TRAÇÃO CALCULADA (A<sub>s,calc</sub>)</div>
            <div class="formula">A<sub>s,base</sub> = F<sub>cc</sub> / f<sub>yd</sub> (kN/cm²) = {Fcc:.2f} / {fyd*0.1:.2f} = {base_as:.2f} cm²</div>
""")
        if arm_dupla:
            html_parts.append(f"""
            <div class="formula">A<sub>s,adicional</sub> (parcela dupla) = {As_adicional:.2f} cm²</div>
            <div class="formula"><strong>A<sub>s,calc</sub> = A<sub>s,base</sub> + A<sub>s,adicional</sub> = {As_calc:.2f} cm²</strong></div>
""")
        else:
            html_parts.append(f"""
            <div class="formula"><strong>A<sub>s,calc</sub> = A<sub>s,base</sub> = {As_calc:.2f} cm²</strong></div>
""")
        html_parts.append("</div>")

        # 10. As,min
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">📉 10. ÁREA MÍNIMA DE ARMADURA (A<sub>s,min</sub>) – NBR 6118</div>
            <div class="formula">ρ<sub>mín</sub> = max(0,26·f<sub>ctm</sub>/f<sub>yk</sub>, 0,0013)</div>
            <div class="formula">f<sub>ctm</sub> = {fctm:.2f} MPa &nbsp;→ 0,26·f<sub>ctm</sub>/f<sub>yk</sub> = {0.26*fctm/fyk:.6f}</div>
            <div class="formula">ρ<sub>mín</sub> = {rho_min:.6f}</div>
            <div class="formula">b<sub>w</sub> = {bw:.2f} cm &nbsp; d = {d:.2f} cm</div>
            <div class="formula">A<sub>s,min</sub> = ρ<sub>mín</sub> · b<sub>w</sub> · d = {rho_min:.6f} × {bw:.2f} × {d:.2f} = {As_min:.2f} cm²</div>
        </div>
""")

        # 11. Armadura adotada
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">📌 11. ARMADURA ADOTADA</div>
            <div class="formula">A<sub>s,adot</sub> = max(A<sub>s,calc</sub>, A<sub>s,min</sub>) = {As_adotar:.2f} cm²</div>
""")
        if arm_dupla:
            html_parts.append(f"""
            <div class="formula">Armadura de compressão A'<sub>s</sub> = {As_linha:.2f} cm² (cobrimento d' = {d_linha:.1f} cm)</div>
""")
        html_parts.append("</div>")

        # 12. Verificações finais
        status_global = "badge-ok" if secao_ok and ductil_ok else "badge-warning"
        status_text = "Seção adequada" if secao_ok and ductil_ok else "Seção requer atenção"
        html_parts.append(f"""
        <div class="section">
            <div class="section-title">📋 12. VERIFICAÇÕES NORMATIVAS FINAIS</div>
            <table class="value-table">
                <tr><td>Seção suficiente (domínio 2 ou 3):</td><td>{'✅ Sim' if secao_ok else '❌ Não'}</td></tr>
                <tr><td>Ductilidade (k<sub>x</sub> ≤ k<sub>x,lim</sub>):</td><td>{'✅ Atende' if ductil_ok else '❌ Não atende'}</td></tr>
                <tr><td>Status geral:</td><td><span class="badge {status_global}">{status_text}</span></td></tr>
            </table>
""")
        if alertas:
            html_parts.append('<div class="alert"><strong>⚠️ Alertas:</strong><ul>')
            for al in alertas:
                html_parts.append(f"<li>{al}</li>")
            html_parts.append("</ul></div>")
        html_parts.append("</div>")

        # Fechamento
        html_parts.append("""
    </div>
    <div class="footer">
        Gerado por Girder25 • NBR 6118:2023 • {data}
    </div>
</div>
</body>
</html>
""".replace("{data}", "2025"))

        html_formatado = "\n".join(html_parts)
        return texto_plano, html_formatado


# ════════════════════════════════════════════════════════════════════════════════
# 3. FUNÇÃO DE DESENHO COM ZONA COMPRIMIDA
# ════════════════════════════════════════════════════════════════════════════════

def desenhar_resultado_flexao(
    dados: Dict,
    resultado: ResultadoDimensionamento,
    geometria: Optional[ParametrosGeometricos] = None,
    h_laje: Optional[float] = None,
    b_laje: Optional[float] = None,
    titulo: str = "Seção Transversal com Zona Comprimida",
    figsize: Tuple[float, float] = (6, 8),
    dpi: int = 100,
) -> plt.Figure:
    """
    Gera desenho técnico da seção com hachura na zona comprimida.

    Características:
        • Desenha a geometria completa da seção
        • Hachura verde na zona comprimida (bloco de compressão)
        • Linha neutra tracejada em vermelho
        • Legenda com resultados principais
        • Suporta seções com laje colaborante

    Código de cores:
        • Fundo: Cinza escuro (#2b2b2b) — profissional e legível
        • Estrutura: Cinza (#555555)
        • Contorno: Branco
        • Zona comprimida: Verde claro (#2ecc71) — intuitividade
        • Linha neutra: Vermelho (#e74c3c) — destaque crítico
        • Laje: Azul suave (#6a8fa8)

    Args:
        dados: Dicionário com dados da seção (Tipo, bw, h, etc.)
        resultado: ResultadoDimensionamento com resultados do cálculo
        geometria: ParametrosGeometricos (opcional), para validação adicional
        h_laje: Altura da laje colaborante [cm], se existir
        b_laje: Largura colaborante [cm], se existir
        titulo: Título da figura
        figsize: Tamanho da figura em polegadas (width, height)
        dpi: Resolução em pontos por polegada

    Returns:
        matplotlib.figure.Figure com o desenho gerado
    """

    # ─── Paleta de cores (tema profissional) ─────────────────────────────────
    cor_fundo = "#2b2b2b"
    cor_estrutura = "#555555"
    cor_contorno = "white"
    cor_zona_comprimida = "#2ecc71"  # Verde claro — intuitivo e profissional
    cor_ln = "#e74c3c"  # Vermelho — destaca a linha neutra
    cor_laje = "#6a8fa8"  # Azul suave
    cor_texto = "white"

    # ─── Criação da figura ────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi, facecolor=cor_fundo)
    ax.set_facecolor(cor_fundo)

    # ─── Obtenção das dimensões da seção ──────────────────────────────────────
    h_base = dados.get("h", 0.0)
    h_total = h_base + (h_laje if h_laje else 0.0)

    # Obtém coordenadas do polígono da seção
    try:
        path_coords = gerar_poligono_secao(dados)
    except Exception as e:
        # Se gerar_poligono_secao falhar, desenha retângulo aproximado
        bw = dados.get("bw", 50.0)
        path_coords = [(-bw / 2, 0), (bw / 2, 0), (bw / 2, h_base), (-bw / 2, h_base)]

    # ─── Desenho da seção principal ────────────────────────────────────────────
    secao_patch = patches.Polygon(
        path_coords,
        closed=True,
        facecolor=cor_estrutura,
        edgecolor=cor_contorno,
        linewidth=1.5,
        zorder=2,
    )
    ax.add_patch(secao_patch)

    # ─── Desenho da laje colaborante (se existir) ─────────────────────────────
    if h_laje is not None and b_laje is not None:
        laje_coords = [
            (-b_laje / 2, h_base),
            (b_laje / 2, h_base),
            (b_laje / 2, h_base + h_laje),
            (-b_laje / 2, h_base + h_laje),
        ]
        laje_patch = patches.Polygon(
            laje_coords,
            closed=True,
            facecolor=cor_laje,
            edgecolor=cor_contorno,
            linewidth=1.5,
            zorder=2,
        )
        ax.add_patch(laje_patch)

    # ─── Cálculo da profundidade do bloco de compressão ──────────────────────
    a = resultado.a  # profundidade do bloco (a = λ·x)

    # Define os limites da zona comprimida conforme o sinal do momento
    if resultado.sinal_momento == "positivo":
        # Compressão no topo → bloco desce de h_total
        y_topo_comp = h_total
        y_base_comp = h_total - a
    else:
        # Compressão na base → bloco sobe de y=0
        y_base_comp = 0.0
        y_topo_comp = a

    # ─── Desenho do bloco de compressão com hachura ───────────────────────────
    rect_compressao = patches.Rectangle(
        (-5000, y_base_comp),
        10000,
        (y_topo_comp - y_base_comp),
        facecolor=cor_zona_comprimida,
        alpha=0.65,
        hatch="\\\\\\\\",
        edgecolor=None,
        zorder=3,
    )
    ax.add_patch(rect_compressao)

    # Aplicar clipping: a zona comprimida só aparece dentro da seção (+ laje)
    if h_laje is not None and b_laje is not None:
        path_composto = Path.make_compound_path(
            secao_patch.get_path(), laje_patch.get_path()
        )
        patch_clip = patches.PathPatch(path_composto, visible=False)
        ax.add_patch(patch_clip)
        rect_compressao.set_clip_path(patch_clip)
    else:
        rect_compressao.set_clip_path(secao_patch)

    # ─── Desenho da linha neutra ──────────────────────────────────────────────
    if resultado.sinal_momento == "positivo":
        y_ln = h_total - resultado.x
    else:
        y_ln = resultado.x

    ax.axhline(
        y_ln,
        color=cor_ln,
        linestyle="--",
        linewidth=2.0,
        zorder=4,
        label="Linha Neutra",
    )

    # Anotação da linha neutra
    ax.text(
        0,
        y_ln + 2,
        f"Linha Neutra (x = {resultado.x:.2f} cm)",
        color=cor_ln,
        ha="center",
        fontsize=9,
        weight="bold",
        zorder=5,
    )

    # ─── Caixa de informações ─────────────────────────────────────────────────
    info_text = (
        f"Momento: {abs(resultado.Msd):.2f} kN·m ({resultado.sinal_momento.upper()})\n"
        f"Profundidade bloco (a): {a:.2f} cm\n"
        f"Posição L.N. (x): {resultado.x:.2f} cm\n"
        f"Índice kx: {resultado.kx:.4f} / {resultado.kx_lim:.2f}\n"
        f"As calculada: {resultado.As_calc:.2f} cm²\n"
        f"As mínima: {resultado.As_min:.2f} cm²\n"
        f"As adotar: {resultado.As_adotar:.2f} cm²"
    )

    status_emoji = "✓" if not resultado.secao_insuficiente else "✗"
    if resultado.armadura_dupla_necessaria:
        status_emoji = "⚠"
        info_text += (
            f"\n\nArmadura Dupla:\n"
            f"A's = {resultado.As_linha:.2f} cm²\n"
            f"ΔM = {resultado.delta_M:.2f} kN·m"
        )

    props_caixa = dict(
        boxstyle="round,pad=0.8",
        facecolor="black",
        alpha=0.75,
        edgecolor=cor_contorno,
        linewidth=1.5,
    )
    ax.text(
        0.02,
        0.98,
        f"{status_emoji} " + info_text,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="top",
        color=cor_texto,
        bbox=props_caixa,
        zorder=6,
        family="monospace",
    )

    # ─── Ajuste automático dos limites ────────────────────────────────────────
    if path_coords:
        largura_max = max([abs(pt[0]) for pt in path_coords])
    else:
        largura_max = dados.get("bw", 50) / 2

    if b_laje:
        largura_max = max(largura_max, b_laje / 2)

    margem = 20
    ax.set_xlim(-largura_max - margem, largura_max + margem)
    ax.set_ylim(-margem, h_total + margem)

    # ─── Formatação final ──────────────────────────────────────────────────────
    ax.set_aspect("equal")
    ax.axis("off")
    fig.suptitle(titulo, fontsize=12, color=cor_contorno, weight="bold", y=0.98)
    plt.tight_layout()

    return fig


# ════════════════════════════════════════════════════════════════════════════════
# 4. EXEMPLO SIMPLES PARA TESTE (gera e exibe o HTML do memorial)
# ════════════════════════════════════════════════════════════════════════════════

def exemplo_simples():
    """
    Executa um único dimensionamento de exemplo e imprime o HTML do memorial.
    Útil para testar a formatação do relatório em tema escuro.
    """
    print("=" * 80)
    print("EXEMPLO DE DIMENSIONAMENTO - GERAÇÃO DO MEMORIAL HTML")
    print("=" * 80)

    # Cria a calculadora com ductilidade normal (pode ser alterada para ESPECIAL)
    calc = CalculadoraFlexaoSimples(ductilidade=ClasseDuctilidade.NORMAL)

    # Define uma seção: Retangular + Laje colaborante (típica de ponte)
    dados_secao = {
        "Tipo": "Retangular",
        "bw": 40.0,   # largura da viga (cm)
        "h": 100.0    # altura da viga (cm)
    }

    # Parâmetros do dimensionamento
    Msd = 450.0          # kN·m (momento positivo)
    d_pos = 92.0         # altura útil para momento positivo (cm)
    d_neg = 90.0         # altura útil para momento negativo (cm)
    fck = 35.0           # MPa
    fyk = 500.0          # MPa
    h_laje = 20.0        # altura da laje colaborante (cm)
    b_laje = 180.0       # largura colaborante (cm)

    print("\n🔹 Dados de entrada:")
    print(f"   Seção: {dados_secao['Tipo']} (bw={dados_secao['bw']} cm, h={dados_secao['h']} cm)")
    print(f"   Laje colaborante: h={h_laje} cm, b={b_laje} cm")
    print(f"   Msd = {Msd} kN·m (positivo)")
    print(f"   d_pos = {d_pos} cm | d_neg = {d_neg} cm")
    print(f"   fck = {fck} MPa | fyk = {fyk} MPa")
    print("-" * 80)

    # Executa o dimensionamento
    resultado = calc.dimensionar(
        dados=dados_secao,
        Msd=Msd,
        d_pos=d_pos,
        d_neg=d_neg,
        fck=fck,
        fyk=fyk,
        h_laje=h_laje,
        b_laje=b_laje,
        d_linha_armadura=5.0,
        calcular_armadura_dupla=True,
    )

    # Obtém o relatório em HTML
    texto_plano, html_memorial = calc.obter_relatorio_resumido()

    # Salva o HTML em um arquivo para inspeção
    with open("memorial_flexao.html", "w", encoding="utf-8") as f:
        f.write(html_memorial)

    print("\n✅ Memorial HTML gerado e salvo como 'memorial_flexao.html'")
    print("\n📄 Conteúdo do HTML (primeiras 500 caracteres):")
    print("-" * 80)
    print(html_memorial[:500] + "...\n")
    print("-" * 80)
    print("Para visualizar, abra o arquivo 'memorial_flexao.html' em um navegador.")
    print("=" * 80)


if __name__ == "__main__":
    exemplo_simples()