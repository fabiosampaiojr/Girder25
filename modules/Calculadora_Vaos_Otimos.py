"""
Calculadora_Vaos_Otimos.py
================================================================================
Módulo de pré-dimensionamento para distribuição de vãos inicial recomendada para pré-dimensionamento.
Baseado em princípios analíticos de equilíbrio de momentos fletores máximos
(positivos e negativos) para otimização do consumo de materiais na superestrutura.

Funcionalidades:
    • Cálculo para Isostática com Balanços Simétricos (Proporção de 20,7%).
    • Cálculo para Hiperestática de 3 Vãos sem Balanço (Relação de 80-85%).
    • Cálculo para Hiperestática Contínua com Balanços (Pontes e Viadutos complexos).
    • Cálculo para Isostática de Múltiplos Vãos Biapoiados (Divisão equitativa).
    • Geração de memoriais de cálculo detalhados em Texto e HTML (Tema Escuro),
      respeitando a terminologia formal da engenharia estrutural.

Autor: Assistente AI de Engenharia
Data: 2026
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum

# ════════════════════════════════════════════════════════════════════════════════
# 1. ESTRUTURAS DE DADOS
# ════════════════════════════════════════════════════════════════════════════════

class SistemaEstrutural(Enum):
    BIAPOIADA                 = "biapoiada"
    ISOSTATICA_EM_BALANCO     = "isostatica_em_balanco"
    HIPERESTATICA_SEM_BALANCO = "hiperestatica_sem_balanco"
    HIPERESTATICA_COM_BALANCO = "hiperestatica_com_balanco"

@dataclass
class DistribuicaoVaos:
    """Classe para armazenar as dimensões calculadas e a descrição formal."""
    rotulo: str
    comprimento: float

@dataclass
class ResultadoOtimizacao:
    """Resultados do cálculo de otimização de vãos."""
    sistema_estrutural : SistemaEstrutural
    comprimento_total  : float
    numero_vaos        : int
    distribuicao       : List[DistribuicaoVaos]
    detalhes_teoricos  : Dict[str, str]

# ════════════════════════════════════════════════════════════════════════════════
# 2. MOTOR DE CÁLCULO
# ════════════════════════════════════════════════════════════════════════════════

class CalculadoraVaosOtimos:
    """
    Classe responsável por calcular a distribuição inicial de vãos recomendada para pré-dimensionamento de acordo com
    o Sistema Estrutural selecionado.
    """

    def __init__(self):
        self.ultimo_resultado: Optional[ResultadoOtimizacao] = None

    @staticmethod
    def _ajustar_soma(valores: List[float], total_alvo: float) -> List[float]:
        """
        Arredonda cada valor para uma casa decimal e ajusta o maior (em módulo)
        para que a soma dos arredondados seja exatamente o total alvo (também com uma casa).
        """
        arredondados = [round(v, 1) for v in valores]
        soma_arred = sum(arredondados)
        alvo_arred = round(total_alvo, 1)
        diferenca = alvo_arred - soma_arred

        if diferenca != 0.0:
            # Ajusta o elemento de maior valor absoluto para minimizar a alteração relativa
            idx = max(range(len(arredondados)), key=lambda i: abs(arredondados[i]))
            arredondados[idx] = round(arredondados[idx] + diferenca, 1)

        return arredondados

    def otimizar_vaos(
        self,
        sistema_estrutural_str: str,
        comprimento_total: float,
        numero_vaos: int = 1
    ) -> ResultadoOtimizacao:
        """
        Calcula os vãos ótimos baseando-se no comprimento total.

        Args:
            sistema_estrutural_str: String identificadora do sistema estrutural.
            comprimento_total: Comprimento total da obra de arte especial [m].
            numero_vaos: Número total de vãos (exigido apenas para sistema biapoiado simples).
        """
        try:
            sistema = SistemaEstrutural(sistema_estrutural_str)
        except ValueError:
            raise ValueError(f"Sistema Estrutural não reconhecido: {sistema_estrutural_str}")

        distribuicao = []
        detalhes = {}
        comprimento_total_original = comprimento_total

        if sistema == SistemaEstrutural.ISOSTATICA_EM_BALANCO:
            # Proporção Áurea para equilibrar momento negativo no apoio e positivo no meio
            # a = 0.207 * L_total, L = 0.586 * L_total
            balanco_raw = comprimento_total * 0.207
            vao_central_raw = comprimento_total - (2 * balanco_raw)

            valores_raw = [balanco_raw, vao_central_raw, balanco_raw]
            valores_ajustados = self._ajustar_soma(valores_raw, comprimento_total)

            distribuicao = [
                DistribuicaoVaos("Balanço Inicial", valores_ajustados[0]),
                DistribuicaoVaos("Vão Central", valores_ajustados[1]),
                DistribuicaoVaos("Balanço Final", valores_ajustados[2])
            ]
            detalhes = {
                "Fundamento": "Igualdade entre o momento fletor negativo máximo no apoio e o momento fletor positivo máximo no meio do vão.",
                "Relação Balanço": "Balanço ≈ 20,7% do Comprimento Total",
                "Relação Vão Central": "Vão Central ≈ 58,6% do Comprimento Total"
            }

        elif sistema == SistemaEstrutural.HIPERESTATICA_SEM_BALANCO:
            # Vão externo ~ 80% a 85% do vão central
            # Prático: 31% - 38% - 31%
            vao_externo_raw = comprimento_total * 0.31
            vao_central_raw = comprimento_total - (2 * vao_externo_raw)

            valores_raw = [vao_externo_raw, vao_central_raw, vao_externo_raw]
            valores_ajustados = self._ajustar_soma(valores_raw, comprimento_total)

            distribuicao = [
                DistribuicaoVaos("Vão Externo Inicial", valores_ajustados[0]),
                DistribuicaoVaos("Vão Central", valores_ajustados[1]),
                DistribuicaoVaos("Vão Externo Final", valores_ajustados[2])
            ]
            detalhes = {
                "Fundamento": "Equalização dos momentos fletores positivos máximos nos vãos internos e externos, compensando a ausência de continuidade na extremidade.",
                "Relação Vão Externo": "Vão Externo ≈ 31,0% do Comprimento Total",
                "Relação Vão Central": "Vão Central ≈ 38,0% do Comprimento Total",
                "Proporção Interna": "Vão Externo / Vão Central ≈ 0,816"
            }

        elif sistema == SistemaEstrutural.HIPERESTATICA_COM_BALANCO:
            # Balanço médio de 12.5%
            # Vão externo ~ 77.5% do vão central
            balanco_raw = comprimento_total * 0.125
            comprimento_restante = comprimento_total - (2 * balanco_raw)

            # 2 * V_ext + V_cen = L_rest
            # V_ext = 0.775 * V_cen -> 2 * (0.775 * V_cen) + V_cen = L_rest -> 2.55 * V_cen = L_rest
            vao_central_raw = comprimento_restante / 2.55
            vao_externo_raw = 0.775 * vao_central_raw

            valores_raw = [balanco_raw, vao_externo_raw, vao_central_raw, vao_externo_raw, balanco_raw]
            valores_ajustados = self._ajustar_soma(valores_raw, comprimento_total)

            distribuicao = [
                DistribuicaoVaos("Balanço Inicial", valores_ajustados[0]),
                DistribuicaoVaos("Vão Externo Inicial", valores_ajustados[1]),
                DistribuicaoVaos("Vão Central", valores_ajustados[2]),
                DistribuicaoVaos("Vão Externo Final", valores_ajustados[3]),
                DistribuicaoVaos("Balanço Final", valores_ajustados[4])
            ]
            detalhes = {
                "Fundamento": "Configuração de máxima eficiência estrutural. O balanço introduz momento fletor negativo que alivia o vão externo, permitindo vãos centrais mais esbeltos.",
                "Relação Balanço": "Balanço ≈ 12,5% do Comprimento Total",
                "Relação Vão Central": "Vão Central ≈ 29,4% do Comprimento Total",
                "Proporção Interna": "Vão Externo / Vão Central = 0,775"
            }

        elif sistema == SistemaEstrutural.BIAPOIADA:
            if numero_vaos < 1:
                raise ValueError("O número de vãos deve ser maior ou igual a 1.")

            vao_igual_raw = comprimento_total / numero_vaos
            valores_raw = [vao_igual_raw] * numero_vaos
            valores_ajustados = self._ajustar_soma(valores_raw, comprimento_total)

            distribuicao = [
                DistribuicaoVaos(f"Vão Biapoiado {i+1}", valores_ajustados[i])
                for i in range(numero_vaos)
            ]

            detalhes = {
                "Fundamento": "Estrutura isostática sequencial sem continuidade. A divisão equitativa padroniza a pré-fabricação das vigas longitudinais e elementos de apoio.",
                "Metodologia": f"Divisão exata do Comprimento Total em {numero_vaos} segmentos iguais."
            }

        resultado = ResultadoOtimizacao(
            sistema_estrutural=sistema,
            comprimento_total=round(comprimento_total_original, 1),
            numero_vaos=numero_vaos,
            distribuicao=distribuicao,
            detalhes_teoricos=detalhes
        )

        self.ultimo_resultado = resultado
        return resultado

    # ════════════════════════════════════════════════════════════════════════════════
    # 3. GERAÇÃO DE RELATÓRIOS (TEXTO E HTML)
    # ════════════════════════════════════════════════════════════════════════════════

    def _formatar_nome_sistema(self, sistema: SistemaEstrutural) -> str:
        mapa = {
            SistemaEstrutural.BIAPOIADA: "Isostática: Múltiplos Vãos Biapoiados",
            SistemaEstrutural.ISOSTATICA_EM_BALANCO: "Isostática: Biapoiada com Balanços Simétricos",
            SistemaEstrutural.HIPERESTATICA_SEM_BALANCO: "Hiperestática: Contínua sem Balanço",
            SistemaEstrutural.HIPERESTATICA_COM_BALANCO: "Hiperestática: Contínua com Balanços"
        }
        return mapa.get(sistema, "Desconhecido")

    def obter_relatorios(self) -> Tuple[str, str]:
        """
        Gera o memorial de cálculo detalhado nos formatos Texto e HTML (Tema Escuro).
        """
        if not self.ultimo_resultado:
            msg = "Nenhum cálculo de otimização realizado ainda."
            return msg, f"<p>{msg}</p>"

        res = self.ultimo_resultado
        nome_sistema = self._formatar_nome_sistema(res.sistema_estrutural)

        # ─────────────────────────────────────────────────────────────────────
        #  RELATÓRIO TEXTO
        # ─────────────────────────────────────────────────────────────────────
        SEP_D = "=" * 80
        SEP_S = "-" * 80
        SEP_M = "·" * 60

        txt = []
        txt.append(SEP_D)
        txt.append("MEMORIAL DE CÁLCULO – PRÉ-DIMENSIONAMENTO DE VÃOS ÓTIMOS")
        txt.append("Otimização Estrutural Longidutinal")
        txt.append(SEP_D)

        txt.append("")
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 1 – DADOS DE ENTRADA E CONFIGURAÇÃO GLOBAL          │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append(f"  Sistema Estrutural Selecionado : {nome_sistema}")
        txt.append(f"  Comprimento Total da Obra      : {res.comprimento_total:.1f} m")
        if res.sistema_estrutural == SistemaEstrutural.BIAPOIADA:
            txt.append(f"  Quantidade de Vãos Informada   : {res.numero_vaos}")

        txt.append("")
        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 2 – FUNDAMENTAÇÃO TEÓRICA E DIRETRIZES DE PROJETO   │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        for chave, valor in res.detalhes_teoricos.items():
            txt.append(f"  ► {chave}:")
            txt.append(f"    {valor}")
            txt.append("")

        txt.append("┌─────────────────────────────────────────────────────────────┐")
        txt.append("│   SEÇÃO 3 – SÍNTESE DA DISTRIBUIÇÃO INCIAL RECOMENDADA      │")
        txt.append("└─────────────────────────────────────────────────────────────┘")
        txt.append("")
        txt.append(f"  {'COMPONENTE LONGITUDINAL':<35} {'DIMENSÃO [m]':>15} {'PROPORÇÃO [%]':>15}")
        txt.append("  " + SEP_S)

        soma_comprimento = 0.0
        for dist in res.distribuicao:
            prop = (dist.comprimento / res.comprimento_total) * 100
            txt.append(f"  {dist.rotulo:<35} {dist.comprimento:>15.1f} {prop:>15.1f}%")
            soma_comprimento += dist.comprimento

        txt.append("  " + SEP_S)
        txt.append(f"  {'SOMA DE VERIFICAÇÃO':<35} {soma_comprimento:>15.1f} {100.0:>15.1f}%")
        txt.append("")
        txt.append(SEP_D)
        txt.append("FIM DO MEMORIAL DE CÁLCULO")
        txt.append(SEP_D)

        texto_plano = "\n".join(txt)

        # ─────────────────────────────────────────────────────────────────────
        #  RELATÓRIO HTML (TEMA ESCURO)
        # ─────────────────────────────────────────────────────────────────────

        # Montagem das linhas da tabela de detalhes teóricos
        html_teoria = ""
        for chave, valor in res.detalhes_teoricos.items():
            html_teoria += f"""
                <p class="sub-title">► {chave}</p>
                <p style="margin-left: 14px; color: #cbd5e1;">{valor}</p>
            """

        # Montagem das linhas da tabela de distribuição
        linhas_tabela = ""
        for dist in res.distribuicao:
            prop = (dist.comprimento / res.comprimento_total) * 100
            linhas_tabela += f"""
                <tr>
                    <td>{dist.rotulo}</td>
                    <td><strong>{dist.comprimento:.1f}</strong></td>
                    <td style="color: #94a3b8;">{prop:.1f}%</td>
                </tr>
            """

        soma_comprimento_html = sum(d.comprimento for d in res.distribuicao)

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #0f172a; color: #e2e8f0; padding: 20px; font-size: 14px; line-height: 1.6; }}
    .container {{ max-width: 900px; margin: 0 auto; background: #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
    .header {{ background: linear-gradient(135deg, #0f4c75 0%, #3282b8 100%); padding: 28px; text-align: center; color: white; border-bottom: 3px solid #1b263b; }}
    .header h1 {{ margin: 0 0 6px 0; font-size: 1.55em; letter-spacing: 0.5px; }}
    .header p  {{ margin: 0; opacity: 0.8; font-size: 0.92em; }}
    .content {{ padding: 28px; }}
    .section {{ margin-bottom: 28px; border-left: 4px solid #3b82f6; padding: 18px 18px 18px 20px; background: rgba(30,40,60,0.5); border-radius: 0 10px 10px 0; }}
    .section-title {{ font-size: 1.15em; font-weight: bold; color: #93c5fd; margin-bottom: 14px; border-bottom: 1px solid #334155; padding-bottom: 8px; }}
    .sub-title {{ color: #7dd3fc; font-weight: bold; margin: 12px 0 4px 0; font-size: 0.98em; }}
    .info-box {{ background: rgba(15,23,42,0.6); border-radius: 6px; padding: 12px 16px; margin-bottom: 16px; border-left: 3px solid #6366f1; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 0.92em; }}
    th {{ background: #1e3a5f; color: #93c5fd; padding: 10px; text-align: center; border-bottom: 2px solid #3b82f6; }}
    td {{ padding: 10px; border-bottom: 1px solid #1e293b; text-align: center; }}
    tr:hover td {{ background: rgba(59,130,246,0.08); }}
    td:first-child {{ text-align: left; font-weight: 600; color: #e2e8f0; }}
    .footer {{ background: #0f172a; padding: 14px; text-align: center; color: #475569; font-size: 0.82em; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📐 Memorial de Cálculo – Pré-Dimensionamento Longitudinal</h1>
        <p>Distribuição de Vãos inicial recomendada para pré-dimensionamento · Análise Analítica de Equilíbrio de Momentos</p>
    </div>
    <div class="content">

        <div class="section">
            <div class="section-title">📌 SEÇÃO 1 – DADOS DE ENTRADA</div>
            <div class="info-box">
                <p>Sistema Estrutural: <strong style="color: #60a5fa;">{nome_sistema}</strong></p>
                <p>Comprimento Total da Obra: <strong>{res.comprimento_total:.1f} m</strong></p>
                {f'<p>Quantidade de Vãos: <strong>{res.numero_vaos}</strong></p>' if res.sistema_estrutural == SistemaEstrutural.BIAPOIADA else ''}
            </div>
        </div>

        <div class="section">
            <div class="section-title">📚 SEÇÃO 2 – FUNDAMENTAÇÃO TEÓRICA E DIRETRIZES</div>
            {html_teoria}
        </div>

        <div class="section">
            <div class="section-title">✅ SEÇÃO 3 – SÍNTESE DA DISTRIBUIÇÃO RECOMENDADA</div>
            <table>
                <thead>
                    <tr>
                        <th>Componente Longitudinal</th>
                        <th>Dimensão [m]</th>
                        <th>Proporção [%]</th>
                    </tr>
                </thead>
                <tbody>
                    {linhas_tabela}
                    <tr style="background: rgba(15,23,42,0.8); border-top: 2px solid #334155;">
                        <td>SOMA DE VERIFICAÇÃO</td>
                        <td><strong>{soma_comprimento_html:.1f}</strong></td>
                        <td style="color: #94a3b8;">100.0%</td>
                    </tr>
                </tbody>
            </table>
        </div>

    </div>
    <div class="footer">
        Memorial de Cálculo gerado automaticamente pelo BridgeCalc · Pré-Dimensionamento Avançado
    </div>
</div>
</body>
</html>
"""
        return texto_plano, html

# ════════════════════════════════════════════════════════════════════════════════
# 4. BATERIA DE TESTES E EXPORTAÇÃO
# ════════════════════════════════════════════════════════════════════════════════

def executar_testes():
    """
    Executa testes para os 4 sistemas estruturais e gera arquivos HTML independentes
    para análise da apresentação visual e acurácia matemática.
    """
    calc = CalculadoraVaosOtimos()
    comprimento_teste = 120.0 # 120 metros para testar as divisões

    cenarios = [
        ("isostatica_em_balanco", comprimento_teste, 1, "memorial_otimizacao_1_isostatica_balanco.html"),
        ("hiperestatica_sem_balanco", comprimento_teste, 1, "memorial_otimizacao_2_hiper_sem_balanco.html"),
        ("hiperestatica_com_balanco", comprimento_teste, 1, "memorial_otimizacao_3_hiper_com_balanco.html"),
        ("biapoiada", comprimento_teste, 4, "memorial_otimizacao_4_multiplos_vaos.html")
    ]

    print("=" * 80)
    print("VALIDAÇÃO: CÁLCULO DE VÃOS ÓTIMOS - BRIDGE CALC")
    print("=" * 80)

    for sistema, comp, vaos, arquivo_saida in cenarios:
        print(f"\n[Testando Sistema]: {sistema}")

        # Executa o cálculo
        resultado = calc.otimizar_vaos(sistema, comp, vaos)

        # Imprime verificação sumária no console
        print(f"  Comprimento Base: {resultado.comprimento_total:.1f} m")
        for dist in resultado.distribuicao:
            print(f"  - {dist.rotulo:<25}: {dist.comprimento:>8.1f} m")

        # Recupera e salva os memoriais
        _, html = calc.obter_relatorios()

        with open(arquivo_saida, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"  [✓] Relatório exportado: {arquivo_saida}")

if __name__ == "__main__":
    executar_testes()