def get_html_status_sistema(tipo=None, vao=None):
    """
    Gera o código HTML em linha única para a label de status do Sistema Estrutural.
    
    Args:
        tipo (str): Tipo do sistema (ex: 'Isostático', 'Hiperestático').
        vao (float): Vão total da ponte em metros.
    Returns:
        str: String formatada em HTML.
    """
    
    # Configurações de estilo
    color_pendente = "#BBBBBB"  # Cinza claro
    color_sucesso = "#81C784"   # Verde suave
    color_destaque = "#64B5F6"  # Azul claro para dados técnicos
    font_size = "13px"          # Fonte levemente aumentada
    
    if tipo is None or vao is None:
        # Estado 1: Pendente
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_pendente};'><span style='color: #FFB74D;'>●</span> <i>Definir o tipo de arranjo estrutural (Vãos e Apoios).</i></span>"
    else:
        # Estado 2: Concluído
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'><b>✅ Sistema Definido:</b> <span style='color: {color_destaque};'> {tipo} (Vão Total: <b>{vao} m</b>)</span></span>"

def get_html_status_secao(passeio=None, classe=None):
    """
    Gera o código HTML em linha única para a label de status da Seção Transversal.

    Args:
        passeio (float, optional): Largura do passeio em cm. Se for None ou False, não é exibido.
        classe (str, optional): Classe de projeto da ponte (ex: 'II').
    Returns:
        str: String formatada em HTML.
    """
    # Configurações de estilo
    color_pendente = "#BBBBBB"
    color_sucesso = "#81C784"
    color_destaque = "#64B5F6"
    font_size = "13px"

    # Estado pendente: classe não informada
    if classe is None:
        return (
            f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_pendente};'>"
            f"<span style='color: #FFB74D;'>●</span> <i>Definir a classe de projeto e a largura do passeio.</i>"
            f"</span>"
        )

    # Estado concluído (classe informada)
    # Monta o trecho da classe
    classe_html = f"Classe de Projeto: <b>{classe}</b>"

    # Monta o trecho do passeio, apenas se for um valor válido
    if passeio is not None and passeio is not False:
        passeio_html = f" | Largura do Passeio: <b>{passeio} cm</b>"
    else:
        passeio_html = ""

    return (
        f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'>"
        f"<b>✅ Seção Definida:</b> <span style='color: {color_destaque};'>"
        f"{classe_html}{passeio_html}"
        f"</span></span>"
    )

def get_html_status_superestrutura(n_longarinas=None, h_cm=None, secao_definida=False):
    """
    Gera o código HTML para o status da Superestrutura.
    
    Args:
        n_longarinas (int): Quantidade de longarinas.
        h_cm (float/int): Altura das longarinas em centímetros.
        secao_definida (bool): Status da dependência (Seção Transversal).
    Returns:
        str: String formatada em HTML.
    """
    
    # Configurações de estilo (Padrão BridgeCalc Dark)
    color_bloqueado = "#EF5350" # Vermelho suave para dependência
    color_pendente = "#BBBBBB"  
    color_sucesso = "#81C784"   
    color_destaque = "#64B5F6"  
    font_size = "13px"          
    
    if not secao_definida:
        # Estado 0: Bloqueado (Depende de Seção Transversal)
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Requer definição da Seção Transversal primeiro.</i></span>"

    if n_longarinas is None or h_cm is None:
        # Estado 1: Disponível para preenchimento
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_pendente};'><span style='color: #FFB74D;'>●</span> <i>Definir as dimensões da laje e das longarinas.</i></span>"
    else:
        # Estado 2: Concluído
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'><b>✅ Geometria Definida:</b> <span style='color: {color_destaque};'> <b>{n_longarinas}</b> Longarinas (H = <b>{h_cm} cm</b>)</span></span>"

    """
    Gera o código HTML para o status dos Coeficientes de Impacto.
    
    Args:
        calculado (bool): Se os cálculos já foram realizados.
        sist_definido (bool): Dependência do Sistema Estrutural.
        secao_definida (bool): Dependência da Seção Transversal.
    Returns:
        str: String formatada em HTML.
    """
    
    # Estilos BridgeCalc
    color_bloqueado = "#EF5350" 
    color_pendente = "#BBBBBB"  
    color_sucesso = "#81C784"   
    color_destaque = "#64B5F6"  
    font_size = "13px"          
    
    # Verifica dependências da Etapa 1
    if not (sist_definido and secao_definida):
        dep = "Sist. Estrutural e Seção"
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Requer {dep} definidos.</i></span>"

    if not calculado:
        # Estado 1: Disponível
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_pendente};'><span style='color: #FFB74D;'>●</span> <i>Calcular coeficientes de impacto (CIA, CIV e CNF).</i></span>"
    else:
        # Estado 2: Concluído
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'><b>✅ Coeficientes Definidos:</b> <span style='color: {color_destaque};'>Parâmetros de majoração calculados com sucesso.</span></span>"

def get_html_status_coef_impacto(calculado=False, sistema_definido=False, secao_definida=False):
    """
    Gera o código HTML para o status dos Coeficientes de Impacto com mensagens específicas.
    """
    
    # Estilos BridgeCalc
    color_bloqueado = "#EF5350" 
    color_pendente = "#BBBBBB"  
    color_sucesso = "#81C784"   
    color_destaque = "#64B5F6"  
    font_size = "13px"          
    
    # 1. Verificação de Dependências Específicas
    if not sistema_definido and not secao_definida:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Requer definição do Sistema Estrutural e da Seção Transversal.</i></span>"
    
    if not sistema_definido:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Aguardando definição do Sistema Estrutural.</i></span>"
    
    if not secao_definida:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Aguardando definição da Seção Transversal.</i></span>"

    # 2. Verificação de Cálculo
    if not calculado:
        # Estado: Disponível para execução
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_pendente};'><span style='color: #FFB74D;'>●</span> <i>Calcular coeficientes de amplificação dinâmica (CIA, CIV e CNF).</i></span>"
    else:
        # Estado: Concluído
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'><b>✅ Coeficientes Definidos:</b> <span style='color: {color_destaque};'>Critérios de impacto processados para a estrutura.</span></span>"

def get_html_trem_tipo(q_kn=None, q1_knm=None, q2_knm=None, super_ok=False):
    """
    Gera o código HTML para o status do Trem Tipo Longitudinal.
    
    Args:
        q_kn (float): Carga concentrada Q em kN.
        q1_knm (float): Carga distribuída q1 em kN/m.
        q2_knm (float): Carga distribuída q2 em kN/m.
        super_ok (bool): Status da dependência (Superestrutura).
    Returns:
        str: String formatada em HTML.
    """
    
    # Estilos BridgeCalc
    color_bloqueado = "#EF5350" 
    color_pendente = "#BBBBBB"  
    color_sucesso = "#81C784"   
    color_destaque = "#64B5F6"  
    font_size = "13px"          
    
    if not super_ok:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Requer definição da Superestrutura.</i></span>"

    if q_kn is None or q1_knm is None or q2_knm is None:
        # Estado: Disponível para configuração
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_pendente};'><span style='color: #FFB74D;'>●</span> <i>Configurar cargas móveis longitudinais (Trem Tipo).</i></span>"
    else:
        # Estado: Concluído com índices matemáticos
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'>"
                f"<b>✅ Trem Tipo Configurado:</b> <span style='color: {color_destaque};'>"
                f"Q = <b>{q_kn} kN</b> | "
                f"q<sub>1</sub> = <b>{q1_knm} kN/m</b> | "
                f"q<sub>2</sub> = <b>{q2_knm} kN/m</b>"
                f"</span></span>")

def get_html_esforcos_permanentes(tipo_acao, r_max=None, v_min=None, v_max=None, m_min=None, m_max=None, etapa1_ok=False):
    """
    Gera o código HTML para o status de Peso Próprio ou Sobrecarga.
    
    Args:
        tipo_acao (str): Nome da ação (ex: 'Peso Próprio' ou 'Sobrecarga').
        r_max, v_min, v_max, m_min, m_max (float): Esforços característicos.
        etapa1_ok (bool): True se Sistema, Seção e Superestrutura estiverem definidos.
    """
    
    # Estilos BridgeCalc
    color_bloqueado = "#EF5350" 
    color_pendente = "#BBBBBB"  
    color_sucesso = "#81C784"   
    color_destaque = "#64B5F6"  
    font_size = "13px"          
    num_size = "12px" # Fonte levemente menor para os números
    
    if not etapa1_ok:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Requer conclusão de toda a Etapa 1 (Geometria).</i></span>"

    if any(v is None for v in [r_max, v_min, v_max, m_min, m_max]):
        # Estado: Disponível para cálculo
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_pendente};'><span style='color: #FFB74D;'>●</span> <i>Calcular esforços de {tipo_acao.lower()} (Análise Linear).</i></span>"
    else:
        # Estado: Concluído com envelopes de esforços (Exibição otimizada)
        v_abs_max = max(abs(v_min), abs(v_max))
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'>"
                f"<b>✅ {tipo_acao} Processado:</b> <span style='color: {color_destaque};'>"
                f"|V|<sub>max</sub>: <b><span style='font-size: {num_size};'>{v_abs_max:.3f}</span></b> kN | "
                f"M<sub>min</sub>: <b><span style='font-size: {num_size};'>{m_min:.3f}</span></b> kNm, "
                f"M<sub>max</sub>: <b><span style='font-size: {num_size};'>{m_max:.3f}</span></b> kNm"
                f"</span></span>")

def get_html_status_temperatura(r_max=None, v_min=None, v_max=None, m_min=None, m_max=None, etapa1_ok=False, hiperestatica=False):
    """
    Gera o código HTML para o status da Temperatura com verificação de hiperestaticidade.
    """
    
    # Estilos BridgeCalc
    color_bloqueado = "#EF5350" 
    color_pendente = "#BBBBBB"  
    color_sucesso = "#81C784"   
    color_destaque = "#64B5F6"  
    color_info = "#B39DDB"      # Roxo suave para info teórica
    font_size = "13px"          
    num_size = "12px"
    
    # 1. Verificação de Dependência da Etapa 1
    if not etapa1_ok:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Requer conclusão de toda a Etapa 1 (Geometria).</i></span>"
   
   # 2. Verificação de Hiperestaticidade
    if not hiperestatica:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_info};'><b>ℹ️ Isostática:</b> <i>Variação térmica não gera esforços internos nesta tipologia.</i></span>"

    # 3. Verificação de Cálculo
    if any(v is None for v in [r_max, v_min, v_max, m_min, m_max]):
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_pendente};'><span style='color: #FFB74D;'>●</span> <i>Calcular esforços devidos ao gradiente térmico (ΔT).</i></span>"
    else:
        v_abs_max = max(abs(v_min), abs(v_max))
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'>"
                f"<b>✅ Temperatura Processada:</b> <span style='color: {color_destaque};'>"
                f"|V|<sub>max</sub>: <b><span style='font-size: {num_size};'>{v_abs_max:.3f}</span></b> kN | "
                f"M<sub>min</sub>: <b><span style='font-size: {num_size};'>{m_min:.3f}</span></b> kNm, "
                f"M<sub>max</sub>: <b><span style='font-size: {num_size};'>{m_max:.3f}</span></b> kNm"
                f"</span></span>")

def get_html_status_carga_movel(r_max=None, v_min=None, v_max=None, m_min=None, m_max=None, etapa1_ok=False, etapa2_ok=False):
    """
    Gera o código HTML para o status da Carga Móvel (Envoltória).
    
    Args:
        r_max, v_min, v_max, m_min, m_max (float): Esforços da envoltória móvel.
        etapa1_ok (bool): Status de Sistema, Seção e Superestrutura.
        etapa2_ok (bool): Status de Coeficientes de Impacto e Trem Tipo.
    """
    
    # Estilos BridgeCalc
    color_bloqueado = "#EF5350" 
    color_pendente = "#BBBBBB"  
    color_sucesso = "#81C784"   
    color_destaque = "#64B5F6"  
    font_size = "13px"          
    num_size = "12px"
    
    # 1. Verificação de Dependências em Cascata
    if not etapa1_ok and not etapa2_ok:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Requer conclusão das Etapas 1 (Geometria) e 2 (Configuração Carga Móvel).</i></span>"
    
    if not etapa1_ok:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Aguardando conclusão da Etapa 1 (Geometria).</i></span>"
    
    if not etapa2_ok:
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'><b>⚠️ Bloqueado:</b> <i>Aguardando configuração do Trem Tipo e Coeficientes (Etapa 2).</i></span>"

    # 2. Verificação de Cálculo (Processamento das Linhas de Influência / Envoltórias)
    if any(v is None for v in [r_max, v_min, v_max, m_min, m_max]):
        return f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_pendente};'><span style='color: #FFB74D;'>●</span> <i>Processar envoltórias de esforços da carga móvel.</i></span>"
    else:
        # Estado: Concluído
        v_abs_max = max(abs(v_min), abs(v_max))
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'>"
                f"<b>✅ Carga Móvel Processada:</b> <span style='color: {color_destaque};'>"
                f"|V|<sub>max</sub>: <b><span style='font-size: {num_size};'>{v_abs_max:.3f}</span></b> kN | "
                f"M<sub>min</sub>: <b><span style='font-size: {num_size};'>{m_min:.3f}</span></b> kNm, "
                f"M<sub>max</sub>: <b><span style='font-size: {num_size};'>{m_max:.3f}</span></b> kNm"
                f"</span></span>")

def get_html_status_esforcos_calculo(etapa3_ok=False, calculado=False):
    """
    Gera o código HTML para o status dos Esforços de Cálculo (ELU & ELS).
    
    Args:
        etapa3_ok (bool): Status da conclusão do Cálculo dos Esforços (Etapa 3).
        calculado (bool): Indica se o processamento final dos esforços foi realizado.
    """
    
    # Estilos BridgeCalc (Mantidos para consistência)
    color_bloqueado = "#EF5350"  # Vermelho
    color_pendente = "#FFB74D"   # Laranja (Ajustado para o ícone de pendência)
    color_sucesso = "#81C784"    # Verde
    font_size = "13px"
    
    # 1. Verificação de Dependência (Bloqueio)
    if not etapa3_ok:
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'>"
                f"<b>⚠️ Bloqueado:</b> <i>Requer conclusão da Etapa 3 (Cálculo dos Esforços).</i></span>")
    
    # 2. Verificação de Processamento (Pendente vs Concluído)
    if not calculado:
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: #BBBBBB;'>"
                f"<span style='color: {color_pendente};'>●</span> <i>Calcular os Esforços de Cálculo (ELU & ELS).</i></span>")
    else:
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_sucesso};'>"
                f"<b>✅ Sucesso:</b> Esforços de Cálculo calculados!</span>")

def get_html_status_armadura_longitudinal(esforcos_calculo_ok=False):
    """
    Gera o código HTML para o status do botão de Cálculo da Armadura Longitudinal.

    Args:
        esforcos_calculo_ok (bool): Indica se os Esforços de Cálculo (ELU & ELS) já foram definidos.
    """
    
    # Estilos consistentes com o BridgeCalc
    color_bloqueado = "#EF5350"  # Vermelho
    color_pendente = "#FFB74D"   # Laranja (ação disponível)
    font_size = "13px"
    
    if not esforcos_calculo_ok:
        # Estado bloqueado: dependência não atendida
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'>"
                f"<b>⚠️ Bloqueado:</b> <i>Primeiro defina os Esforços de Cálculo (ELU e ELS).</i></span>")
    else:
        # Estado disponível: o usuário pode prosseguir com a ação
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: #BBBBBB;'>"
                f"<span style='color: {color_pendente};'>●</span> <i>Calcular armadura longitudinal e verificar fadiga.</i></span>")  

def get_html_status_armadura(esforcos_calculo_ok=False, armadura="longitudinal"):
    """
    Gera o código HTML para o status do botão de Cálculo da Armadura (Longitudinal ou Transversal).

    Args:
        esforcos_calculo_ok (bool): Indica se os Esforços de Cálculo (ELU & ELS) já foram definidos.
        armadura (str): Tipo de armadura: "longitudinal" (padrão) ou "transversal".
    """
    
    # Estilos consistentes com o BridgeCalc
    color_bloqueado = "#EF5350"  # Vermelho
    color_pendente = "#FFB74D"   # Laranja (ação disponível)
    font_size = "13px"
    
    if not esforcos_calculo_ok:
        # Estado bloqueado: dependência não atendida
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: {color_bloqueado};'>"
                f"<b>⚠️ Bloqueado:</b> <i>Primeiro defina os Esforços de Cálculo (ELU e ELS).</i></span>")
    else:
        # Estado disponível: o usuário pode prosseguir com a ação
        texto_acao = f"Calcular armadura {armadura} e verificar fadiga."
        return (f"<span style='font-family: Segoe UI; font-size: {font_size}; color: #BBBBBB;'>"
                f"<span style='color: {color_pendente};'>●</span> <i>{texto_acao}</i></span>")