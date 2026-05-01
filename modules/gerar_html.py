import re
from typing import Dict, Tuple, Optional, Literal


def gerar_html_memorial_coef(coeficiente):
    """
    Gera um fragmento HTML com a explicação e fórmulas de um coeficiente
    utilizado no cálculo de impacto em pontes, seguindo um tema visual escuro
    e profissional.
    
    Parâmetros:
    - coeficiente (str): Nome do coeficiente (case insensitive). Opções:
        'cia', 'civ', 'cnf', 'impacto'.
    
    Retorna:
    - str: Conteúdo HTML formatado para exibição em interfaces web.
    """
    # Estilos base reutilizáveis (inline para facilitar incorporação)
    container_style = (
        "style='"
        "font-family: Arial, sans-serif; font-size: 12px; line-height: 1.2; "
        "color: #E0E0E0; background-color: #1E1E1E; padding: 16px; "
        "border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);'"
    )
    titulo_style = (
        "style='margin: 0 0 8px 0; color: #64B5F6; font-size: 16px; "
        "font-weight: 600; border-bottom: 1px solid #333; padding-bottom: 4px;'"
    )
    formula_style = (
        "style='font-family: \"Courier New\", monospace; font-weight: bold; "
        "color: #FFB74D; font-size: 15px; margin: 12px 0; text-align: center;'"
    )
    nota_style = (
        "style='margin: 8px 0 0 0; font-style: italic; color: #AAAAAA; "
        "font-size: 11px;'"
    )

    # Abre o container principal
    html = f"<div {container_style}>"

    # Geração do conteúdo conforme o coeficiente solicitado
    if coeficiente.lower() == "cia":
        html += f"""
            <h3 {titulo_style}>Impacto Adicional (CIA)</h3>
            <p>Considera efeitos dinâmicos decorrentes de acidentes e imperfeições em juntas.</p>
            <p>O <strong>CIA</strong> assume valor diferente de 1,00 apenas em distâncias inferiores a 5m das juntas.</p>
            <table style='width: 100%; margin-top: 8px; color: #E0E0E0;'>
                <tr>
                    <td style='padding: 4px 0;'>• Concreto / Mistas:</td>
                    <td style='padding: 4px 0;'><span {formula_style}>CIA = 1,25</span></td>
                </tr>
                <tr>
                    <td style='padding: 4px 0;'>• Estruturas em Aço:</td>
                    <td style='padding: 4px 0;'><span {formula_style}>CIA = 1,15</span></td>
                </tr>
            </table>
        """

    elif coeficiente.lower() == "civ":
        html += f"""
            <h3 {titulo_style}>Impacto Vertical (CIV)</h3>
            <p>Majorador que considera as variações dinâmicas da carga móvel.</p>
            <div {formula_style}>
                CIV = 1 + 1,06 &middot; [ 20 / (L<sub>iv</sub> + 50) ]
            </div>
            <p {nota_style}><strong>Nota:</strong> Para L<sub>iv</sub> &lt; 10 m, o valor de CIV é limitado a 1,35 (valor máximo).</p>
            <p style='margin: 8px 0 4px 0;'><strong>Onde L<sub>iv</sub></strong> (vão de inércia) é definido como:</p>
            <ul style='margin: 4px 0 0 16px; padding-left: 0;'>
                <li>Para vigas isostáticas: comprimento do vão.</li>
                <li>Para vigas contínuas: média aritmética dos vãos.</li>
                <li>Para balanços: comprimento do próprio balanço.</li>
            </ul>
        """

    elif coeficiente.lower() == "cnf":
        html += f"""
            <h3 {titulo_style}>Número de Faixas (CNF)</h3>
            <p>Considera a influência de múltiplas faixas de tráfego (N) no carregamento.</p>
            <div {formula_style}>
                CNF = 1 - 0,05 &middot; (N - 2) &ge; 0,9
            </div>
            <p {nota_style}>Nota: Aplicado apenas em elementos longitudinais.</p>
        """

    elif coeficiente.lower() == "impacto":
        html += f"""
            <h3 {titulo_style}>Coeficiente de Impacto (ϕ)</h3>
            <p>Resultado final do produto das parcelas majoradoras:</p>
            <div style='font-family: \"Courier New\", monospace; font-weight: bold; 
                        color: #81C784; font-size: 20px; text-align: center; 
                        margin: 16px 0; padding: 12px; background-color: #2A2A2A; 
                        border-radius: 6px;'>
                ϕ = CIA · CIV · CNF
            </div>
        """

    else:
        html += f"""
            <p {nota_style}>Coeficiente não identificado. Opções válidas: CIA, CIV, CNF, Impacto.</p>
        """

    # Fecha o container principal
    html += "</div>"
    return html


def obter_html_trem_tipo(tipo_trem: str) -> str:
    """
    Retorna um HTML estilizado com as características do trem-tipo selecionado,
    incluindo nome, símbolos, valores numéricos, unidades e referência normativa.

    Parâmetros
    ----------
    tipo_trem : str
        Identificador do trem-tipo. Valores aceitos:
        - "tb_450" → TB-450 (NBR 7188:2024)
        - "tb_240" → TB-240 (NBR 7188:2024)

    Retorna
    -------
    str
        Código HTML formatado para exibição em QLabel.
    """
    # Cores do tema escuro (consistentes com outras funções)
    cor_fundo   = "#1e1e1e"
    cor_texto   = "#e0e0e0"
    cor_titulo  = "#90caf9"
    cor_valor   = "#4ade80"
    cor_borda   = "#333333"
    cor_norma   = "#888888"

    # Mapeamento dos trens-tipo (atualizado para NBR 7188:2024)
    trens = {
        "tb_450": {
            "nome": "TB-450",
            "P": "75",
            "q": "5",
            "norma": "NBR 7188:2024"
        },
        "tb_240": {
            "nome": "TB-240",
            "P": "40",
            "q": "4",
            "norma": "NBR 7188:2024"
        }
    }

    if tipo_trem not in trens:
        return f"""
        <div style="background-color: {cor_fundo}; padding: 15px; text-align: center;
                    border-radius: 8px; border: 1px solid {cor_borda};">
            <span style="color: {cor_texto};">Trem-tipo não reconhecido.</span>
        </div>
        """

    dados = trens[tipo_trem]
    nome = dados["nome"]
    p_val = dados["P"]
    q_val = dados["q"]
    norma = dados["norma"]

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: {cor_texto};
                background-color: {cor_fundo}; padding: 18px; border-radius: 8px;
                border: 1px solid {cor_borda}; text-align: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
        <!-- Título principal -->
        <div style="font-size: 16pt; font-weight: bold; color: {cor_titulo};
                    margin-bottom: 12px;">
            {nome}
        </div>

        <!-- Descrição das cargas -->
        <div style="background-color: #252525; padding: 16px; border-radius: 6px;
                    margin-bottom: 12px;">
            <div style="margin-bottom: 15px;">
                <span style="font-size: 13pt; color: {cor_texto};">
                    Carga por eixo (<i>P</i>):
                </span>
                <br>
                <span style="font-size: 18pt; font-weight: bold; color: {cor_valor};
                             font-family: 'Courier New', monospace;">
                    {p_val} kN
                </span>
            </div>
            <div>
                <span style="font-size: 13pt; color: {cor_texto};">
                    Carga distribuída (<i>q</i>):
                </span>
                <br>
                <span style="font-size: 18pt; font-weight: bold; color: {cor_valor};
                             font-family: 'Courier New', monospace;">
                    {q_val} kN/m²
                </span>
            </div>
        </div>

        <!-- Referência normativa -->
        <div style="font-size: 9pt; color: {cor_norma}; margin-top: 8px;">
            Referência: {norma}
        </div>
    </div>
    """
    return html


def gerar_html_xi2(n, sum_xi2):
    """
    Gera o memorial de cálculo em HTML com a expansão de n em linha única.
    """
    # Cálculos
    inv_n = 1 / n if n != 0 else 0
    
    # Formatação (4 casas para precisão de coeficientes, 2 para somatórios)
    str_n = str(n)
    str_inv_n = f"{inv_n:.4f}"
    str_sum = f"{sum_xi2:.2f}"

    html = f"""
    <div style="font-family: 'Times New Roman', serif; color: white;">
        <table border="0" cellpadding="0" cellspacing="0" style="vertical-align: middle; border-collapse: collapse; margin-bottom: 15px;">
            <tr>
                <td style="padding-right: 8px; font-size: 18pt; vertical-align: middle; border: none;">
                    <i>&eta;<sub>ij</sub></i> =
                </td>
                <td style="vertical-align: middle; border: none;">
                    <table border="0" cellpadding="0" cellspacing="0" style="width: 100%; border-collapse: collapse;">
                        <tr><td style="text-align: center; border-bottom: 1.5px solid white; padding: 0 5px; font-size: 14pt;">1</td></tr>
                        <tr><td style="text-align: center; padding: 0 5px; font-size: 14pt;"><i>n</i></td></tr>
                    </table>
                </td>
                <td style="padding: 0 12px; font-size: 16pt; vertical-align: middle; border: none;"> + </td>
                <td style="vertical-align: middle; border: none;">
                    <table border="0" cellpadding="0" cellspacing="0" style="width: 100%; border-collapse: collapse;">
                        <tr><td style="text-align: center; border-bottom: 1.5px solid white; padding: 0 10px; font-size: 14pt;"><i>x<sub>i</sub></i> · <i>x<sub>j</sub></i></td></tr>
                        <tr><td style="text-align: center; padding: 0 10px; font-size: 14pt;"><span style="font-size: 16pt;">&sum;</span> <i>x<sub>i</sub></i><sup>2</sup></td></tr>
                    </table>
                </td>
            </tr>
        </table>

        <div style="font-size: 12pt; border-left: 2px solid #555; padding-left: 15px; line-height: 2.0;">
            <div style="display: block; margin-bottom: 10px;">
                • <i>n</i> = {str_n} &nbsp; &rarr; &nbsp; 1 / {str_n} = <b>{str_inv_n}</b>
            </div>
            <div style="display: block;">
                • &sum; <i>x<sub>i</sub></i><sup>2</sup> = <b>{str_sum} cm²</b>
            </div>
        </div>
    </div>
    """
    return html


def gerar_html_propriedades_secao(parametros_geometricos, unidade="cm"):
    """
    Gera HTML centralizado otimizado para QLabel 251x291px.
    Equilíbrio entre legibilidade e espaço (Fonte 12pt).

    Exibe as seguintes propriedades:
        - Área da Seção (A): área composta (longarina + laje, se houver)
        - Área da Longarina (A_long): área apenas da longarina, sem laje colaborante
          (exibida somente quando a chave "Area Longarina" estiver presente)
        - Momento de Inércia (Ix)
        - Posição do Centroide (ycg)
        - Altura Total da Seção (h)
    """
    if unidade == "m":
        k = 0.01
        u_linear, u_area, u_inertia = "m", "m²", "m⁴"
    else:
        k = 1.0
        u_linear, u_area, u_inertia = "cm", "cm²", "cm⁴"

    valores = {
        "Area": parametros_geometricos["Area"] * (k**2),
        "Ix": parametros_geometricos["Ix"] * (k**4),
        "ycg": parametros_geometricos["ycg"] * k,
        "h": parametros_geometricos["h"] * k
    }

    # Inclui Área da Longarina apenas quando disponível (seção com laje colaborante)
    area_long_raw = parametros_geometricos.get("Area Longarina")
    if area_long_raw is not None:
        valores["Area Longarina"] = area_long_raw * (k**2)

    def formatar(valor):
        if valor != 0 and (abs(valor) < 0.0001 or abs(valor) > 10000000):
            return f"{valor:.3e}"
        return f"{valor:.3f}"

    # Linha opcional para a área da longarina (exibida apenas quando presente)
    linha_area_long = ""
    if "Area Longarina" in valores:
        linha_area_long = (
            f"Área da Longarina (<b><i>A<sub>long</sub></i></b>): "
            f"<b>{formatar(valores['Area Longarina'])} {u_area}</b><br>"
        )

    # Fonte 12pt com line-height 2.5 garante o preenchimento sem estourar.
    html = f"""
    <div style="font-family: 'Times New Roman', serif; color: white;">
        <table border="0" cellpadding="0" cellspacing="0" style="width: 251px; height: 291px; text-align: center; border-collapse: collapse;">
            <tr>
                <td style="vertical-align: middle; border: none;">
                    <div style="line-height: 2.5; white-space: nowrap; font-size: 12pt;">
                        Área da Seção (<b><i>A</i></b>): <b>{formatar(valores['Area'])} {u_area}</b><br>
                        {linha_area_long}Momento de Inércia (<b><i>I<sub>x</sub></i></b>): <b>{formatar(valores['Ix'])} {u_inertia}</b><br>
                        Posição do Centroide (<b><i>y<sub>cg</sub></i></b>): <b>{formatar(valores['ycg'])} {u_linear}</b><br>
                        Altura Total da Seção (<b><i>h</i></b>): <b>{formatar(valores['h'])} {u_linear}</b>
                    </div>
                </td>
            </tr>
        </table>
    </div>
    """
    return html


def gerar_html_calculo_area(h_laje, l_laje, n_longarinas, area_longarina, ativo=True):
    """
    Gera o HTML formatado para o cálculo da área total da seção transversal.
    Se ativo=False, a cor de destaque do resultado torna-se cinza.
    """
    # Cor do destaque baseada no estado ativo
    cor_destaque = "#2ecc71" if ativo else "#888888"

    # Cálculos internos
    a_laje_valor = h_laje * l_laje
    a_longarinas_total = area_longarina * n_longarinas
    a_total = a_laje_valor + a_longarinas_total

    # Montagem do HTML com estilo equação e fonte branca
    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white;'>
        <div style='white-space: nowrap;'>
            <b>A<sub>laje</sub></b> = h<sub>laje</sub> &times; L<sub>laje</sub> 
            = {h_laje} &times; {l_laje} 
            = <b>{a_laje_valor:.2f} cm²</b>
            
            <span style='margin: 0 10px; color: #7f8c8d;'> | </span>
            
            <b>A<sub>longarinas</sub></b> = A<sub>longarina</sub> &times; n&ordm;<sub>longarinas</sub> 
            = {area_longarina} &times; {n_longarinas} 
            = <b>{a_longarinas_total:.2f} cm²</b>
        </div>
        <div style='white-space: nowrap; margin-top: 8px;'>
            <b>A<sub>total</sub></b> = A<sub>laje</sub> + A<sub>longarinas</sub> 
            = <span style='color: {cor_destaque};'><b>{a_total:.2f} cm²</b></span>
        </div>
    </body>
    </html>
    """
    return html


def gerar_html_carga_g1(a_total, gama_c, n_longarinas, ativo=True):
    """
    Gera o HTML formatado para o cálculo da carga permanente g1.
    Se ativo=False, a cor de destaque do resultado torna-se cinza.
    """
    # Cor do destaque baseada no estado ativo
    cor_destaque = "#2ecc71" if ativo else "#888888"

    g1_valor = a_total * gama_c / n_longarinas

    # Montagem do HTML
    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white;'>
        <div style='white-space: nowrap;'>
            <b>g<sub>1</sub></b> = A<sub>total</sub> &times; &gamma;<sub>c</sub> / n&ordm;<sub>longarinas</sub>
            = {a_total:.4f} &times; {gama_c} / {n_longarinas}
            = <span style='color: {cor_destaque};'><b>{g1_valor:.2f} kN/m</b></span>
        </div>
    </body>
    </html>
    """
    return html


def gerar_html_resultados_esforcos(r_max, v_min, v_max, m_min, m_max):
    # Estrutura com fonte branca, sem cores extras, apenas negrito nos resultados
    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white; line-height: 1.6;'>
        <div style='padding: 5px;'>
            <b>Reação de Apoio:</b><br>
            R<sub>max</sub> = <b>{r_max:.2f} kN</b>
            
            <br><br>
            
            <b>Cortante:</b><br>
            V<sub>min</sub> = <b>{v_min:.2f} kN</b> | V<sub>max</sub> = <b>{v_max:.2f} kN</b>
            
            <br><br>
            
            <b>Momento Fletor:</b><br>
            M<sub>min</sub> = <b>{m_min:.2f} kNm</b> e M<sub>max</sub> = <b>{m_max:.2f} kNm</b>
        </div>
    </body>
    </html>
    """
    return html


def gerar_html_pavimento(l_pavimento, h_centro, h_borda, gama_pavimento, ativo=True):
    """
    Gera o HTML centralizado para a carga do pavimento (g2) em duas linhas.
    Cálculo: g2,pav = L_pavimento * ((h_centro + h_borda) / 2) * gama_pavimento
    Se ativo=False, a cor de destaque do resultado torna-se cinza.
    """
    # Cor do destaque baseada no estado ativo
    cor_destaque = "#2ecc71" if ativo else "#888888"

    # Cálculo interno (Média das alturas)
    g2_pav_valor = l_pavimento * ((h_centro + h_borda) / 2) * gama_pavimento

    # Montagem do HTML centralizado
    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white; text-align: center;'>
        <div style='white-space: nowrap;'>
            <b>g<sub>2,pavimento</sub></b> = L<sub>pavimento</sub> &times; [ (h<sub>centro</sub> + h<sub>borda</sub>) / 2 ] &times; &gamma;<sub>pavimento</sub> 
        </div>
        <div style='white-space: nowrap; margin-top: 5px;'>
            = {l_pavimento:.2f} &times; [ ({h_centro:.2f} + {h_borda:.2f}) / 2 ] &times; {gama_pavimento:.2f} 
            = <span style='color: {cor_destaque};'><b>{g2_pav_valor:.2f} kN/m</b></span>
        </div>
    </body>
    </html>
    """
    return html


def gerar_html_guarda_rodas(area_guarda_rodas, gama_concreto, ativo=True):
    """
    Gera o HTML para a carga dos guarda-rodas (g2).
    Cálculo: g2_guarda-rodas = 2 * (Area_gr * gama_c)
    Se ativo=False, a cor de destaque do resultado torna-se cinza.
    """
    # Cor do destaque baseada no estado ativo
    cor_destaque = "#2ecc71" if ativo else "#888888"

    # Cálculo interno considerando as duas extremidades
    g2_gr_valor = 2 * (area_guarda_rodas * gama_concreto)

    # Montagem do HTML em linha única seguindo rigorosamente o padrão
    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white;'>
        <div style='white-space: nowrap;'>
            <b>g<sub>2,guarda-rodas</sub></b> = 2 &times; (A<sub>guarda-rodas</sub> &times; &gamma;<sub>c</sub>)
            <span style='margin: 0 10px; color: #7f8c8d;'> | </span>
            = 2 &times; ({area_guarda_rodas:.4f} &times; {gama_concreto:.2f}) 
            = <span style='color: {cor_destaque};'><b>{g2_gr_valor:.2f} kN/m</b></span>
        </div>
    </body>
    </html>
    """
    return html


def gerar_html_repavimentacao(l_pavimento, q_repavimentacao, ativo=True):
    """
    Gera o HTML para a carga de repavimentação (g2).
    Cálculo: g2,repavimentacao = L_pavimento * q_repavimentacao
    Se ativo=False, a cor de destaque do resultado torna-se cinza.
    """
    # Cor do destaque baseada no estado ativo
    cor_destaque = "#2ecc71" if ativo else "#888888"

    # Cálculo interno
    g2_repav_valor = l_pavimento * q_repavimentacao

    # Montagem do HTML em linha única
    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white;'>
        <div style='white-space: nowrap;'>
            <b>g<sub>2,repavimentação</sub></b> = L<sub>pavimento</sub> &times; q<sub>repavimentação</sub> 
            <span style='margin: 0 10px; color: #7f8c8d;'> | </span>
            = {l_pavimento:.2f} &times; {q_repavimentacao:.2f} 
            = <span style='color: {cor_destaque};'><b>{g2_repav_valor:.2f} kN/m</b></span>
        </div>
    </body>
    </html>
    """
    return html


def gerar_html_sobrecarga_passeio(l_passeio, h_passeio, gama_pavimento, q_guarda_corpo, n, ativo=True):
    """
    Gera o HTML para a carga do passeio (g2) em duas linhas.
    Cálculo: g2,passeio = n * (L_passeio * h_passeio * gama_pavimento + q_guarda_corpo)
    Se ativo=False, a cor de destaque do resultado torna-se cinza.
    """
    # Cor do destaque baseada no estado ativo
    cor_destaque = "#2ecc71" if ativo else "#888888"

    # Cálculo interno
    valor_unitario = (l_passeio * h_passeio * gama_pavimento) + q_guarda_corpo
    g2_passeio_total = n * valor_unitario

    # Lógica para o multiplicador n=2
    prefixo = "2 &times; [" if n == 2 else ""
    sufixo = "]" if n == 2 else ""
    
    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white;'>
        <div style='white-space: nowrap;'>
            <b>g<sub>2,passeio</sub></b> = {prefixo}L<sub>passeio</sub> &times; h<sub>passeio</sub> &times; &gamma;<sub>pavimento</sub> + q<sub>guarda-corpo</sub>{sufixo}
        </div>
        <div style='white-space: nowrap; margin-top: 5px;'>
            = {prefixo}{l_passeio:.2f} &times; {h_passeio:.2f} &times; {gama_pavimento:.2f} + {q_guarda_corpo:.2f}{sufixo} 
            = <span style='color: {cor_destaque};'><b>{g2_passeio_total:.2f} kN/m</b></span>
        </div>
    </body>
    </html>
    """
    return html


def gerar_html_g2_total(g2_pav, g2_repav, g2_gr, n_longarinas, g2_passeio=None, ativo=True):
    """
    Gera o HTML centralizado para a soma total de segunda etapa por longarina.
    Cálculo: g2,total = (sum(g2_componentes)) / nº Longarinas
    Se ativo=False, a cor de destaque do resultado torna-se cinza.
    """
    # Cor do destaque baseada no estado ativo
    cor_destaque = "#2ecc71" if ativo else "#888888"

    # Listas para construção dinâmica da fórmula e dos valores
    componentes_nome = ["g<sub>2,pav</sub>", "g<sub>2,repav</sub>", "g<sub>2,gr</sub>"]
    valores_num = [g2_pav, g2_repav, g2_gr]

    # Adiciona o passeio apenas se não for None
    if g2_passeio is not None:
        componentes_nome.append("g<sub>2,pas</sub>")
        valores_num.append(g2_passeio)

    # Montagem das strings da soma
    soma_literal = " + ".join(componentes_nome)
    soma_numerica = " + ".join([f"{v:.2f}" for v in valores_num])
    
    # Cálculo final dividido pelo número de longarinas
    g2_total_valor = sum(valores_num) / n_longarinas

    # HTML centralizado em linha única com fonte 14pt
    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 14pt; color: white; text-align: center;'>
        <div style='white-space: nowrap;'>
            <b>g<sub>2,total</sub></b> = ({soma_literal}) / nº<sub>Longarinas</sub> 
            = ({soma_numerica}) / {n_longarinas} 
            = <span style='color: {cor_destaque};'><b>{g2_total_valor:.2f} kN/m</b></span>
        </div>
    </body>
    </html>
    """
    return html


def gerar_html_trem_tipo(Q, q1, q2):
    """
    Gera HTML para QLabel com fontes equilibradas, 
    termos por extenso e índices subscritos.
    """
    
    html = f"""
    <html>
    <body style='font-family: "Segoe UI", Tahoma, sans-serif; margin: 0; padding: 8px; background-color: #2b2b2b; color: white;'>
        
        <div style='text-align: center; font-size: 11pt; font-weight: bold; color: #ffffff; margin-bottom: 10px; border-bottom: 1px solid #555; padding-bottom: 4px;'>
            Parâmetros Trem-Tipo Longitudinal (Longarina)
        </div>

        <div style='margin-bottom: 8px; padding: 6px; background: rgba(52, 152, 219, 0.1); border-radius: 4px; border-left: 3px solid #3498db;'>
            <span style='font-size: 9pt; color: #3498db; font-weight: bold; text-transform: uppercase;'>Carregamento:</span>
            <span style='font-size: 10pt; margin-left: 10px; color: #eee;'>
                Carga Concentrada (<b>Q</b>): <b>{Q} kN</b>  |  
                Carga Distribuída Externa (<b>q<sub>1</sub></b>): <b>{q1} kN/m</b>  |  
                Carga Distribuída Interna (<b>q<sub>2</sub></b>): <b>{q2} kN/m</b>
            </span>
        </div>

        <div style='padding: 6px; background: rgba(241, 196, 15, 0.05); border-radius: 4px; border-left: 3px solid #f1c40f;'>
            <span style='font-size: 9pt; color: #f1c40f; font-weight: bold; text-transform: uppercase;'>Geometria:</span>
            <span style='font-size: 10pt; margin-left: 10px; color: #ddd;'>
                Espaçamento entre Eixos: <b>150 cm</b>  |  
                Extensão do Veículo: <b>6.00 m</b>  |  
                Largura de Influência: <b>3.00 m</b>
            </span>
        </div>

    </body>
    </html>
    """
    return html


def html_definir_cargas(ativo=True):
    """
    Retorna um dicionário com 3 códigos HTML para os rótulos de carga.
    Se ativo=False, as cores de destaque e bordas tornam-se cinza.
    """
    
    # Definição da Paleta de Cores baseada no estado
    if ativo:
        c_destaque = "#3498db"  # Azul para estado ativo
        c_fundo = "rgba(52, 152, 219, 0.1)"
        c_texto = "#eee"
    else:
        c_destaque = "#7f8c8d"  # Cinza para estado inativo
        c_fundo = "rgba(149, 165, 166, 0.05)"
        c_texto = "#888"

    # Template base para os rótulos
    def criar_label(conteudo):
        return f"""
        <html>
        <body style='font-family: "Segoe UI", Tahoma, sans-serif; margin: 0; padding: 0; background-color: transparent;'>
            <div style='padding: 6px; background: {c_fundo}; border-radius: 4px; border-left: 3px solid {c_destaque}; display: inline-block;'>
                <span style='font-size: 10pt; color: {c_texto};'>{conteudo}</span>
            </div>
        </body>
        </html>
        """

    # Gerando os 3 HTMLs para o dicionário
    dict_html = {
        "html_q":  criar_label("Carga Concentrada (<b>Q</b>):"),
        "html_q1": criar_label("Carga Distribuída Externa (<b>q<sub>1</sub></b>):"),
        "html_q2": criar_label("Carga Distribuída Interna (<b>q<sub>2</sub></b>):")
    }

    return dict_html


def gerar_html_coeficientes(criterio="normativo"):
    """
    Retorna um dicionário com dois HTMLs. 
    O critério selecionado aparece com as cores originais, 
    o outro aparece com cores foscas (desativado).
    """
    
    # Definição de cores para o estado ATIVO
    cor_destaque_ativa = "#f1c40f"
    cor_texto_ativa = "#ffffff"
    cor_borda_ativa = "#444"
    cor_subtexto_ativa = "#aaa"
    
    # Definição de cores para o estado DESATIVADO
    cor_destaque_off = "#555555"
    cor_texto_off = "#777777"
    cor_borda_off = "#333333"
    cor_subtexto_off = "#444444"

    # Lógica de seleção de cores
    if criterio.lower() == "normativo":
        c_norm = {"destaque": cor_destaque_ativa, "texto": cor_texto_ativa, "borda": cor_borda_ativa, "sub": cor_subtexto_ativa}
        c_pers = {"destaque": cor_destaque_off, "texto": cor_texto_off, "borda": cor_borda_off, "sub": cor_subtexto_off}
    else:
        c_norm = {"destaque": cor_destaque_off, "texto": cor_texto_off, "borda": cor_borda_off, "sub": cor_subtexto_off}
        c_pers = {"destaque": cor_destaque_ativa, "texto": cor_texto_ativa, "borda": cor_borda_ativa, "sub": cor_subtexto_ativa}

    html_normativo = f"""
    <html>
    <body style='background-color: #2b2b2b; color: {c_norm['texto']}; font-family: "Segoe UI", sans-serif; padding: 15px;'>
        <table style='width: 100%; border-collapse: collapse; font-size: 10pt; table-layout: fixed;'>
            <tr>
                <td colspan="2" style='padding: 5px 0 10px 0;'>
                    <b style='color: {c_norm['destaque']}; font-size: 11pt;'>COEFICIENTES DE PONDERAÇÃO</b>
                </td>
            </tr>
            <tr style='border-bottom: 1px solid {c_norm['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle; width: 65%;'>Ações permanentes (&gamma;<sub>g</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle; width: 35%;'>1,35 <span style='font-size: 8pt; color: {c_norm['sub']}; font-weight: normal;'>(desf.)</span> / 1,0</td>
            </tr>
            <tr style='border-bottom: 1px solid {c_norm['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Ações variáveis (&gamma;<sub>q</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>1,50</td>
            </tr>
            <tr style='border-bottom: 1px solid {c_norm['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Variações de temperatura (&gamma;<sub>&epsilon;q</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>1,20</td>
            </tr>
            <tr><td colspan="2" style='padding: 10px 0;'></td></tr>
            <tr>
                <td colspan="2" style='padding: 5px 0 10px 0;'>
                    <b style='color: {c_norm['destaque']}; font-size: 11pt;'>FATORES DE COMBINAÇÃO E REDUÇÃO</b>
                </td>
            </tr>
            <tr style='border-bottom: 1px solid {c_norm['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Fator de combinação (&psi;<sub>0</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>0,60</td>
            </tr>
            <tr style='border-bottom: 1px solid {c_norm['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Redução Ação Móvel (&psi;<sub>1</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>0,50</td>
            </tr>
            <tr style='border-bottom: 1px solid {c_norm['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Redução Temperatura (&psi;<sub>2</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>0,30</td>
            </tr>
        </table>
        <div style='font-family: "Segoe UI", sans-serif; font-size: 8.5pt; color: {c_norm['destaque']}; padding-top: 10px; text-align: right; border-top: 1px dashed {c_norm['borda']}; margin-top: 20px;'>
            Referência: NBR 8681:2003
        </div>
    </body>
    </html>"""

    html_personalizado = f"""
    <html>
    <body style='background-color: #2b2b2b; color: {c_pers['texto']}; font-family: "Segoe UI", sans-serif; padding: 15px;'>
        <table style='width: 100%; border-collapse: collapse; font-size: 10pt; table-layout: fixed;'>
            <tr>
                <td colspan="2" style='padding: 5px 0 10px 0;'>
                    <b style='color: {c_pers['destaque']}; font-size: 11pt;'>COEFICIENTES DE PONDERAÇÃO</b>
                </td>
            </tr>
            <tr style='border-bottom: 1px solid {c_pers['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle; width: 65%;'>Ações permanentes (&gamma;<sub>g</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle; width: 35%;'>---</td>
            </tr>
            <tr style='border-bottom: 1px solid {c_pers['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Ações variáveis (&gamma;<sub>q</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>---</td>
            </tr>
            <tr style='border-bottom: 1px solid {c_pers['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Variações de temperatura (&gamma;<sub>&epsilon;q</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>---</td>
            </tr>
            <tr><td colspan="2" style='padding: 10px 0;'></td></tr>
            <tr>
                <td colspan="2" style='padding: 5px 0 10px 0;'>
                    <b style='color: {c_pers['destaque']}; font-size: 11pt;'>FATORES DE COMBINAÇÃO E REDUÇÃO</b>
                </td>
            </tr>
            <tr style='border-bottom: 1px solid {c_pers['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Fator de combinação (&psi;<sub>0</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>---</td>
            </tr>
            <tr style='border-bottom: 1px solid {c_pers['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Redução Ação Móvel (&psi;<sub>1</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>---</td>
            </tr>
            <tr style='border-bottom: 1px solid {c_pers['borda']};'>
                <td style='padding: 8px 0; vertical-align: middle;'>Redução Temperatura (&psi;<sub>2</sub>):</td>
                <td style='text-align: right; font-weight: bold; vertical-align: middle;'>---</td>
            </tr>
        </table>
    </body>
    </html>"""

    return {
        "html_normativo": html_normativo,
        "html_personalizado": html_personalizado
    }


def gerar_html_resultados_esforcos_calculos(
    secoes_criticas: Dict[str, Dict[str, Tuple]],
    tipo_dado: Optional[Literal["calculo", "movel", "estatico"]] = None,
    janela: Optional[Literal["cortante", "momento", "reacoes"]] = None
) -> str:
    """
    Gera HTML estilizado com resultados de esforços críticos (Cortante, Momento Fletor
    e Reações), adaptando-se automaticamente ao tipo de dado fornecido.

    Parâmetros
    ----------
    secoes_criticas : dict
        Dicionário no formato:
            {
                "Cortante": {
                    "Máximo": (label_secao, v_min, v_max),
                    "Mínimo": (label_secao, v_min, v_max)
                },
                "Momento": {...},
                "Reações": {...}
            }
        Para diagramas estáticos (Peso Próprio, Sobrecarga, Temperatura), v_min == v_max.
    tipo_dado : str, opcional
        Pode ser "calculo" (envoltória ELU/ELS), "movel" (carga móvel com φ), ou
        "estatico" (diagrama único). Se omitido, tenta detectar automaticamente.
    janela : str, opcional
        Se fornecido ("cortante", "momento" ou "reacoes"), retorna apenas o card
        correspondente ao esforço solicitado, incluindo sua convenção.
        Se None (padrão), retorna todos os esforços disponíveis.

    Retorna
    -------
    str
        HTML pronto para QLabel (RichText).
    """

    # Cores do tema escuro
    cor_fundo   = "#1e1e1e"
    cor_texto   = "#e0e0e0"
    cor_titulo  = "#90caf9"
    cor_pos     = "#81c784"
    cor_neg     = "#e57373"
    cor_borda   = "#333333"

    def sub(txt: str) -> str:
        return re.sub(r'_(\w+)', r'<sub>\1</sub>', str(txt))

    # Detecta automaticamente o tipo se não informado
    if tipo_dado is None:
        # Verifica se algum valor tem v_min == v_max (típico de estático)
        for casos in secoes_criticas.values():
            for extremo in ("Máximo", "Mínimo"):
                _, vmin, vmax = casos.get(extremo, ("", 0, 0))
                if abs(vmin - vmax) < 1e-6:
                    tipo_dado = "estatico"
                    break
            if tipo_dado:
                break
        if tipo_dado is None:
            tipo_dado = "calculo"  # padrão

    # Prefixo para carga móvel (será usado no título e nos símbolos)
    prefixo = "φ·" if tipo_dado == "movel" else ""

    simbolos = {"Cortante": "V", "Momento": "M", "Reações": "R"}
    unidades = {"Cortante": "kN", "Momento": "kN·m", "Reações": "kN"}

    # Convenções (mantidas centralizadas)
    convencao_momento = """
    <div style="font-family: sans-serif; font-size: 11pt; color: #e0e0e0; text-align: center;">
        <b style="font-size: 13pt; color: #ffffff;">Convenção:</b>
        <div style="margin-top: 8px; border-top: 1px solid #444; padding-top: 8px;">
            <span style="color: #81c784; font-weight: bold;">(+) Positivo:</span> 
            Tração embaixo &rarr; <b>Armadura Inferior</b>
            <br>
            <span style="color: #e57373; font-weight: bold;">(-) Negativo:</span> 
            Tração em cima &rarr; <b>Armadura Superior</b>
        </div>
    </div>
    """

    convencao_cortante = """
    <div style="font-family: sans-serif; font-size: 10pt; color: #e0e0e0; text-align: center;">
        <b style="font-size: 11.5pt; color: #ffffff;">Convenção:</b>
        <div style="margin-top: 6px; border-top: 1px solid #444; padding-top: 6px;">
            <span style="color: #81c784; font-weight: bold;">(+) Cortante Positivo:</span> 
            Rotação horária → <b>Tração diagonal (/) → Estribos</b>
            <br>
            <span style="color: #e57373; font-weight: bold;">(-) Cortante Negativo:</span> 
            Rotação anti-horária → <b>Tração diagonal (\\) → Estribos</b>
        </div>
    </div>
    """

    convencao_reacoes = """
    <div style="font-family: sans-serif; font-size: 10pt; color: #e0e0e0; text-align: center;">
        <b style="font-size: 11.5pt; color: #ffffff;">Convenção:</b>
        <div style="margin-top: 6px; border-top: 1px solid #444; padding-top: 6px;">
            <span style="color: #81c784; font-weight: bold;">(+) Para cima:</span> 
            Reação vertical ascendente.
            <br>
            <span style="color: #e57373; font-weight: bold;">(-) Para baixo:</span> 
            Reação vertical descendente.
        </div>
    </div>
    """

    def formatar_valor_colorido(valor: float, unidade: str = "") -> str:
        cor = cor_pos if valor >= 0 else cor_neg
        valor_str = f"{valor:+.2f}"
        if unidade:
            return f'<span style="color: {cor};">{valor_str} {unidade}</span>'
        return f'<span style="color: {cor};">{valor_str}</span>'

    def gerar_card(esforco: str, casos: dict) -> str:
        s = simbolos.get(esforco, "E")
        u = unidades.get(esforco, "")
        ps = prefixo + s
        # Título: se houver prefixo, deve vir antes do nome do esforço
        titulo = f"{prefixo}{esforco}" if prefixo else esforco

        sec_max, v_min_max, v_max_max = casos["Máximo"]
        sec_min, v_min_min, v_max_min = casos["Mínimo"]

        estatico = (tipo_dado == "estatico")

        if estatico:
            v_max_fmt = formatar_valor_colorido(v_max_max, u)
            v_min_fmt = formatar_valor_colorido(v_min_min, u)

            return f"""
            <div style="margin-bottom: 25px; background-color: #252525; border-radius: 8px;
                        padding: 16px; border: 1px solid {cor_borda}; text-align: center;">
                <div style="font-size: 14pt; font-weight: bold; color: {cor_titulo};
                            margin-bottom: 14px; border-bottom: 1px solid {cor_borda};
                            padding-bottom: 6px;">
                    {titulo}
                </div>
                <div style="margin-bottom: 10px;">
                    <span style="font-size: 11pt; color: {cor_texto};">
                        <b>Máximo em {sec_max}:</b>
                    </span>
                    <br>
                    <span style="font-size: 12.5pt; font-weight: bold;
                                 font-family: 'Courier New', monospace;">
                        {sub(ps + "_max")} = {v_max_fmt}
                    </span>
                </div>
                <div>
                    <span style="font-size: 11pt; color: {cor_texto};">
                        <b>Mínimo em {sec_min}:</b>
                    </span>
                    <br>
                    <span style="font-size: 12.5pt; font-weight: bold;
                                 font-family: 'Courier New', monospace;">
                        {sub(ps + "_min")} = {v_min_fmt}
                    </span>
                </div>
            </div>
            """
        else:
            v_max_fmt   = formatar_valor_colorido(v_max_max, u)
            v_min_max_fmt = formatar_valor_colorido(v_min_max, u)
            v_min_fmt   = formatar_valor_colorido(v_min_min, u)
            v_max_min_fmt = formatar_valor_colorido(v_max_min, u)

            return f"""
            <div style="margin-bottom: 25px; background-color: #252525; border-radius: 8px;
                        padding: 16px; border: 1px solid {cor_borda}; text-align: center;">
                <div style="font-size: 14pt; font-weight: bold; color: {cor_titulo};
                            margin-bottom: 14px; border-bottom: 1px solid {cor_borda};
                            padding-bottom: 6px;">
                    {titulo}
                </div>
                <div style="margin-bottom: 10px;">
                    <span style="font-size: 11pt; color: {cor_texto};">
                        <b>Máximo em {sec_max}:</b>
                    </span>
                    <br>
                    <span style="font-size: 12.5pt; font-weight: bold;
                                 font-family: 'Courier New', monospace;">
                        {sub(ps + "_min")} = {v_min_max_fmt} &nbsp;|&nbsp;
                        {sub(ps + "_max")} = {v_max_fmt}
                    </span>
                </div>
                <div>
                    <span style="font-size: 11pt; color: {cor_texto};">
                        <b>Mínimo em {sec_min}:</b>
                    </span>
                    <br>
                    <span style="font-size: 12.5pt; font-weight: bold;
                                 font-family: 'Courier New', monospace;">
                        {sub(ps + "_min")} = {v_min_fmt} &nbsp;|&nbsp;
                        {sub(ps + "_max")} = {v_max_min_fmt}
                    </span>
                </div>
            </div>
            """

    # --- NOVA LÓGICA PARA O PARÂMETRO 'janela' ---
    # Mapeia o valor do parâmetro para a chave usada em 'secoes_criticas'
    mapa_janela_para_esforco = {
        "cortante": "Cortante",
        "momento": "Momento",
        "reacoes": "Reações"
    }

    if janela is not None:
        # Modo janela específica: retorna apenas o esforço solicitado
        chave_esforco = mapa_janela_para_esforco.get(janela)
        if chave_esforco not in secoes_criticas:
            # Se o esforço não existir nos dados, retorna HTML vazio
            return f"""
            <html>
            <body style="background-color: {cor_fundo}; color: {cor_texto};
                         font-family: 'Segoe UI', Arial, sans-serif; padding: 15px; margin: 0;">
                <div style="max-width: 100%;"></div>
            </body>
            </html>
            """

        # Gera o card e a convenção correspondente
        card = gerar_card(chave_esforco, secoes_criticas[chave_esforco])
        convencao = ""
        if chave_esforco == "Cortante":
            convencao = convencao_cortante
        elif chave_esforco == "Momento":
            convencao = convencao_momento
        elif chave_esforco == "Reações":
            convencao = convencao_reacoes

        html_content = card + convencao
        return f"""
        <html>
        <body style="background-color: {cor_fundo}; color: {cor_texto};
                     font-family: 'Segoe UI', Arial, sans-serif; padding: 15px; margin: 0;">
            <div style="max-width: 100%;">
                {html_content}
            </div>
        </body>
        </html>
        """
    else:
        # Modo padrão: todos os esforços disponíveis (comportamento original)
        html_parts = []
        for esforco in ["Cortante", "Momento", "Reações"]:
            if esforco in secoes_criticas:
                html_parts.append(gerar_card(esforco, secoes_criticas[esforco]))
                if esforco == "Cortante":
                    html_parts.append(convencao_cortante)
                elif esforco == "Momento":
                    html_parts.append(convencao_momento)
                elif esforco == "Reações":
                    html_parts.append(convencao_reacoes)
                html_parts.append("<br>")

        if html_parts and html_parts[-1] == "<br>":
            html_parts.pop()

        html_content = "\n".join(html_parts)

        return f"""
        <html>
        <body style="background-color: {cor_fundo}; color: {cor_texto};
                     font-family: 'Segoe UI', Arial, sans-serif; padding: 15px; margin: 0;">
            <div style="max-width: 100%;">
                {html_content}
            </div>
        </body>
        </html>
        """

# ============================================================================
# BLOCO DE TESTES ROBUSTO (ATUALIZADO)
# ============================================================================
if __name__ == "__main__":
    # 1. Esforços de Cálculo (ELU/ELS)
    secoes_calculo = {
        "Cortante": {
            "Máximo": ("S10 (45.00 m)", -50.3, 1029.3),
            "Mínimo": ("S5 (22.50 m)", -200.0, 573.2)
        },
        "Momento": {
            "Máximo": ("S7 (31.50 m)", -1200.0, 3500.8),
            "Mínimo": ("S2 (9.00 m)", -2500.5, 800.0)
        },
        "Reações": {
            "Máximo": ("Apoio A (0.00 m)", -150.0, 320.5),
            "Mínimo": ("Apoio B (60.00 m)", -200.0, 50.0)
        }
    }
    html1 = gerar_html_resultados_esforcos_calculos(secoes_calculo, tipo_dado="calculo")
    with open("teste_esforcos_calculo.html", "w", encoding="utf-8") as f:
        f.write(html1)
    print("✅ 'teste_esforcos_calculo.html' gerado (ELU/ELS).")

    # 2. Carga Móvel (com φ) – títulos agora como "φ·Cortante"
    secoes_movel = {
        "Cortante": {
            "Máximo": ("S10 (45.00 m)", -30.0, 850.0),
            "Mínimo": ("S5 (22.50 m)", -180.0, 400.0)
        },
        "Momento": {
            "Máximo": ("S7 (31.50 m)", -950.0, 2800.0),
            "Mínimo": ("S2 (9.00 m)", -2100.0, 600.0)
        },
        "Reações": {
            "Máximo": ("Apoio A (0.00 m)", -120.0, 280.0),
            "Mínimo": ("Apoio B (60.00 m)", -160.0, 40.0)
        }
    }
    html2 = gerar_html_resultados_esforcos_calculos(secoes_movel, tipo_dado="movel")
    with open("teste_esforcos_movel.html", "w", encoding="utf-8") as f:
        f.write(html2)
    print("✅ 'teste_esforcos_movel.html' gerado (Carga Móvel).")

    # 3. Diagramas Estáticos (Peso Próprio, Sobrecarga, Temperatura)
    secoes_estatico = {
        "Cortante": {
            "Máximo": ("S10 (45.00 m)", 300.0, 300.0),
            "Mínimo": ("S5 (22.50 m)", -150.0, -150.0)
        },
        "Momento": {
            "Máximo": ("S7 (31.50 m)", 1200.0, 1200.0),
            "Mínimo": ("S2 (9.00 m)", -800.0, -800.0)
        },
        "Reações": {
            "Máximo": ("Apoio A (0.00 m)", 500.0, 500.0),
            "Mínimo": ("Apoio B (60.00 m)", 200.0, 200.0)
        }
    }
    html3 = gerar_html_resultados_esforcos_calculos(secoes_estatico, tipo_dado="estatico")
    with open("teste_esforcos_estatico.html", "w", encoding="utf-8") as f:
        f.write(html3)
    print("✅ 'teste_esforcos_estatico.html' gerado (Diagramas Estáticos).")

    # 4. Detecção automática para estático
    html4 = gerar_html_resultados_esforcos_calculos(secoes_estatico)
    with open("teste_esforcos_autodetect.html", "w", encoding="utf-8") as f:
        f.write(html4)
    print("✅ 'teste_esforcos_autodetect.html' gerado (detecção automática).")

    print("\nTodos os arquivos HTML foram criados com sucesso.")