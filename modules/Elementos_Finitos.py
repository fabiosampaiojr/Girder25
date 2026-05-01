import numpy as np
from typing import List, Sequence, Union, Optional
from numpy.polynomial.legendre import leggauss
Number = Union[int, float]
import copy
import matplotlib.pyplot as plt
import time
from scipy.integrate import cumulative_trapezoid as cumtrapz
import math
# Importações de paralelismo agora ativadas
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing


def numeric_element_stiffness(I, E, A, L, theta_deg):
    """
    Retorna a matriz de rigidez global do elemento (6x6)
    em coordenadas globais, já rotacionada pelo ângulo theta.
    """
    # Converte graus para radianos
    theta = np.radians(theta_deg)

    # Cosseno e seno
    c = np.cos(theta)
    s = np.sin(theta)

    # ----- Matriz de rigidez local (em coordenadas locais) -----
    Ke_local = np.array([
        [E*A/L, 0, 0, -E*A/L, 0, 0],
        [0, 12*E*I/L**3, 6*E*I/L**2, 0, -12*E*I/L**3, 6*E*I/L**2],
        [0, 6*E*I/L**2, 4*E*I/L, 0, -6*E*I/L**2, 2*E*I/L],
        [-E*A/L, 0, 0, E*A/L, 0, 0],
        [0, -12*E*I/L**3, -6*E*I/L**2, 0, 12*E*I/L**3, -6*E*I/L**2],
        [0, 6*E*I/L**2, 2*E*I/L, 0, -6*E*I/L**2, 4*E*I/L]
    ])

    # ----- Matriz de transformação -----
    T = np.array([
        [ c,  s, 0,  0,  0, 0],
        [-s,  c, 0,  0,  0, 0],
        [ 0,  0, 1,  0,  0, 0],
        [ 0,  0, 0,  c,  s, 0],
        [ 0,  0, 0, -s,  c, 0],
        [ 0,  0, 0,  0,  0, 1]
    ])

    # ----- Matriz de rigidez global -----
    Ke_global = T.T @ Ke_local @ T

    return Ke_global

def build_nodes_from_inputs(
    supports: Sequence[Sequence],
    concentrated_forces: Sequence[Sequence],
    section_params: Sequence[Sequence],
    *,
    round_to: Optional[int] = 0,
    as_numpy: bool = False,
    tol: float = 1e-6) -> Union[List[Number], np.ndarray]:
    
    """
    Retorna as coordenadas únicas e ordenadas dos nós a partir das entradas:
      - supports: [[x, 'tipo'], ...]
      - concentrated_forces: [[x, Fy, ...], ...]  (aceita listas com >=1 item)
      - section_params: [[x_start, x_end, ...], ...] (cada secção deve ter pelo menos 2 itens)
    
    Parâmetros extras:
      - round_to: se int (ex.: 0 -> arredonda para inteiro; 3 -> arredonda para 10^(-3)),
                  se None -> não arredonda (mantém float).
      - as_numpy: se True, retorna um np.ndarray; senão, retorna lista Python.
      - tol: tolerância para considerar valores iguais quando round_to é None (combina coordenadas muito próximas).
    
    Retorno:
      - lista ordenada de coordenadas (inteiros se round_to == 0 por padrão).
    
    Complexidade: O(n) para coletar valores + O(m log m) para ordenação/unique (m = # de coordenadas coletadas).
    """
    xs = []

    # helpers para extrair a coordenada x (assume que o primeiro item da linha é x)
    def _safe_x(entry):
        if entry is None or len(entry) == 0:
            return None
        try:
            return float(entry[0])
        except Exception:
            return None

    # supports
    for s in supports or []:
        x = _safe_x(s)
        if x is not None:
            xs.append(x)

    # concentrated forces
    for f in concentrated_forces or []:
        x = _safe_x(f)
        if x is not None:
            xs.append(x)

    # section boundaries (x_start, x_end)
    for sec in section_params or []:
        if sec is None:
            continue
        if len(sec) >= 1:
            x0 = _safe_x([sec[0]])
            if x0 is not None:
                xs.append(x0)
        if len(sec) >= 2:
            x1 = _safe_x([sec[1]])
            if x1 is not None:
                xs.append(x1)

    if len(xs) == 0:
        out = np.array([], dtype=float) if as_numpy else []
        return out

    xs = np.asarray(xs, dtype=float)

    # Arredondamento / eliminação de duplicatas:
    if round_to is not None:
        # round_to == 0 -> inteiros; round_to > 0 -> casas decimais
        if round_to == 0:
            xs_rounded = np.round(xs).astype(int)
        else:
            xs_rounded = np.round(xs, round_to)
        uniq = np.unique(xs_rounded)
        # se round_to == 0 devolvemos ints
        if round_to == 0:
            out = uniq.astype(int)
        else:
            out = uniq
    else:
        # Sem arredondamento: eliminamos valores muito próximos usando tolerância
        xs_sorted = np.sort(xs)
        uniq = [xs_sorted[0]]
        for val in xs_sorted[1:]:
            if abs(val - uniq[-1]) > tol:
                uniq.append(val)
        out = np.array(uniq)

    if as_numpy:
        return np.asarray(out)
    else:
        # converter para lista e se forem valores inteiros implícitos, convertê-los para int
        if isinstance(out, np.ndarray) and np.issubdtype(out.dtype, np.integer):
            return out.tolist()
        else:
            # se todos os valores tiverem parte fracionária zero -> convert to int
            if np.allclose(np.mod(out.astype(float), 1.0), 0.0, atol=1e-9):
                return [int(x) for x in out.tolist()]
            return out.tolist()

def add_points_from_inputs(
    supports: list[list[Union[int, float, str]]],
    concentrated_forces: list[list[Union[int, float]]] | None,
    nodes_x: list[Number]
):
    """
    Cria lista de nós com informações de forças, deslocamentos e rotações.
    Cada nó contém:
      [x, Fx, Fy, M, u, v, rot]

    As incógnitas permanecem como strings (ex: 'Fy3'),
    e forças concentradas são armazenadas como tuplas:
        ('Fy3', -10000, -5000)
    para facilitar a separação entre variáveis e valores numéricos.

    Retorna:
        points            -> lista de nós (com valores simbólicos e numéricos)
        unknowns_labels   -> lista das incógnitas simbólicas (strings)
    """

    # === 1. Cria os pontos base ===
    points = []
    for i, x in enumerate(nodes_x, start=1):
        points.append([x, f'Fx{i}', f'Fy{i}', f'M{i}', f'u{i}', f'v{i}', f'rot{i}'])

    # === 2. Identifica coordenadas de apoios ===
    x_supports = [float(s[0]) for s in supports or []]

    # === 3. Zera reações nos nós sem apoio ===
    for p in points:
        if p[0] not in x_supports:
            p[1] = 0  # Fx
            p[2] = 0  # Fy
            p[3] = 0  # M

    # === 4. Função auxiliar para achar índice por coordenada x ===
    def idx_by_x(xval: Number) -> int:
        for idx, p in enumerate(points):
            if abs(p[0] - xval) < 1e-6:
                return idx
        return -1

    # === 5. Aplica condições de contorno dos suportes ===
    for x_sup, sup_type in supports or []:
        idx = idx_by_x(float(x_sup))
        if idx == -1:
            raise ValueError(f"Support at x={x_sup} not found in node list.")

        typ = sup_type.lower()
        if typ == 'fix':      # engaste
            points[idx][3] = 0  # M = 0
            points[idx][4] = 0  # u = 0
            points[idx][5] = 0  # v = 0
        elif typ == 'mov':    # apoio móvel
            points[idx][3] = 0  # M = 0
            points[idx][1] = 0  # Fx = 0
            points[idx][5] = 0  # v = 0
        elif typ == 'pin':    # rótula
            points[idx][3] = 0  # M = 0
            points[idx][4] = 0  # u = 0
            points[idx][5] = 0  # v = 0
        else:
            raise ValueError(f"Unknown support type '{typ}'. Use 'fix','mov','pin'.")

    # === 6. Aplica forças concentradas ===
    for x_f, Fy_value in concentrated_forces or []:
        idx = idx_by_x(float(x_f))
        if idx == -1:
            # Este erro pode ocorrer se a lógica de geração de nós não incluir
            # todas as posições de força. A função build_nodes_from_inputs
            # deve garantir que todas as posições de força sejam nós.
            raise ValueError(f"Force at x={x_f} not found in node list. (Nós: {[p[0] for p in points]})")

        current = points[idx][2]

        # Caso 1: número puro
        if isinstance(current, (int, float)):
            points[idx][2] = current + Fy_value

        # Caso 2: símbolo puro (ex: 'Fy3')
        elif isinstance(current, str):
            points[idx][2] = (current, Fy_value)

        # Caso 3: já é tupla (símbolo + valores extras)
        elif isinstance(current, tuple):
            points[idx][2] = current + (Fy_value,)

        else:
            raise TypeError(f"Unexpected type for Fy entry at node x={x_f}: {type(current)}")


    return points      

def apply_distributed_loads_bulk(points: list[list], distributed_loads: list[list[Number]], n_gauss: int = 8):
    """
    Aplica carregamentos distribuídos a um conjunto de pontos (nós) de viga.

    distributed_loads: lista de [x_start, q_start, x_end, q_end].
        q_start e q_end em N/mm (ou unidade coerente).
        O carregamento é interpolado linearmente entre x_start e x_end.

    Atualiza in-place:
        points[i][2] += Fy_left
        points[i][3] += M_left
        points[i+1][2] += Fy_right
        points[i+1][3] += M_right
    """

    if not distributed_loads:
        return points  # nada a fazer

    # --- função auxiliar: interpolação linear q(x) ---
    def make_qfunc(x0, q0, x1, q1):
        if x1 == x0:
            return lambda x: float(q0)
        return lambda x: q0 + (q1 - q0) * (x - x0) / (x1 - x0)

    # --- integração sobre os elementos ---
    for x_start, q_start, x_end, q_end in distributed_loads:
        qfunc = make_qfunc(x_start, q_start, x_end, q_end)

        for i in range(len(points) - 1):
            xe = points[i][0]
            xf = points[i + 1][0]

            # Intervalo de interseção entre o elemento e o carregamento
            a = max(xe, min(x_start, x_end))
            b = min(xf, max(x_start, x_end))
            if b <= a:
                continue  # elemento fora da faixa do carregamento

            L_elem = xf - xe
            s_a, s_b = a - xe, b - xe

            # Pontos e pesos de Gauss
            gp, gw = leggauss(n_gauss)
            s_mid = 0.5 * (s_b + s_a)
            s_half = 0.5 * (s_b - s_a)
            s_pts = s_mid + s_half * gp
            w_pts = gw * s_half

            # Vetor de forças locais do carregamento distribuído
            fe_local = np.zeros(4, dtype=float)

            for s, w in zip(s_pts, w_pts):
                xi = s / L_elem
                # Funções de forma de Hermite para vigas 2D
                N1 = 1 - 3*xi**2 + 2*xi**3
                N2 = L_elem * (xi - 2*xi**2 + xi**3)
                N3 = 3*xi**2 - 2*xi**3
                N4 = L_elem * (-xi**2 + xi**3)
                Nvec = np.array([N1, N2, N3, N4])
                qx = float(qfunc(xe + s))
                fe_local += Nvec * qx * w

            # --- atualização dos nós ---
            def add_to_point(idx_pt: int, slot: int, value: float):
                cur = points[idx_pt][slot]

                # Caso 1: número puro
                if isinstance(cur, (int, float)):
                    points[idx_pt][slot] = cur + value

                # Caso 2: símbolo puro (ex: 'Fy3') → transforma em tupla (símbolo, valor)
                elif isinstance(cur, str):
                    points[idx_pt][slot] = (cur, value)

                # Caso 3: já é tupla → acumula mais um valor
                elif isinstance(cur, tuple):
                    points[idx_pt][slot] = cur + (value,)

                else:
                    raise TypeError(f"Unsupported type {type(cur)} at node {idx_pt}, slot {slot}")

            add_to_point(i,   2, fe_local[0])  # Fy left
            add_to_point(i,   3, fe_local[1])  # M left
            add_to_point(i+1, 2, fe_local[2])  # Fy right
            add_to_point(i+1, 3, fe_local[3])  # M right

    return points

def boundary_conditions(points):
    """
    Extrai os vetores de forças (F) e deslocamentos (U) a partir da lista 'points'.

    Estrutura de cada ponto:
        [x, Fx, Fy, M, Ux, Uy, θ]

    Retorna:
        F (np.ndarray[str | float]): vetor com forças/momentos
        U (np.ndarray[str | float]): vetor com deslocamentos/rotações
    """
    F = np.array([val for p in points for val in p[1:4]], dtype=object)
    U = np.array([val for p in points for val in p[4:7]], dtype=object)
    return F, U

def elements_generator_with_sections(points, section_params):
    """
    Gera a lista de elementos e o total de graus de liberdade (GDL).

    Cada elemento tem a estrutura:
        [I_, E_, A_, L_, theta_deg, g1, g2, g3, g4, g5, g6]

    Args:
        points: lista de pontos [[x, Fx, Fy, M, u, v, rot], ...]
        section_params: [[x_ini, x_fim, I, E, A, theta], ...]

    Returns:
        elements: lista de elementos
        total_dof: número total de graus de liberdade
    """
    n_nodes = len(points)
    if n_nodes < 2:
        raise ValueError("É necessário ao menos dois nós para formar um elemento.")

    elements = []

    for i in range(1, n_nodes):
        x_left = float(points[i - 1][0])
        x_right = float(points[i][0])
        L_elem = x_right - x_left
        if L_elem <= 0:
            raise ValueError(f"Elemento com comprimento inválido entre x={x_left} e x={x_right}.")

        x_mid = 0.5 * (x_left + x_right)

        # Localiza a seção correspondente
        matched = None
        for xs, xe, I, E, A, theta in section_params:
            if min(xs, xe) <= x_mid <= max(xs, xe):
                matched = (float(I), float(E), float(A), float(theta))
                break
        if matched is None:
            raise ValueError(f"Nenhuma seção cobre o ponto médio x={x_mid}.")

        I_, E_, A_, theta_ = matched

        # GDLs globais (3 por nó)
        gdl_start = (i - 1) * 3 + 1
        gdl_end = gdl_start + 5
        dofs = list(range(gdl_start, gdl_end + 1))

        element = [I_, E_, A_, L_elem, theta_, *dofs]
        elements.append(element)

    total_dof = n_nodes * 3
    return elements, total_dof

def assemble_global_stiffness(K_elements, total_dof):
    """
    Monta a matriz de rigidez global do sistema a partir das matrizes de rigidez
    elementares (K_elements) e do total de graus de liberdade (total_dof).

    Parâmetros:
    ------------
    K_elements : list of np.ndarray
        Lista de matrizes 7x7 (saída de beam_numeric)
        Cada matriz tem a primeira linha e coluna com índices globais (g1..g6)
    total_dof : int
        Número total de graus de liberdade do sistema

    Retorna:
    --------
    K_global : np.ndarray
        Matriz de rigidez global (total_dof x total_dof)
    """
    # Inicializa a matriz global cheia de zeros
    K_global = np.zeros((total_dof, total_dof), dtype=float)

    # Percorre cada matriz de rigidez elementar
    for Ke in K_elements:
        # Extrai os índices globais (ajustando para base 0)
        GDL = Ke[0, 1:].astype(int) - 1  # [g1, g2, g3, g4, g5, g6]

        # Adiciona as contribuições do elemento à matriz global
        # (usando slicing para melhor desempenho)
        for i in range(6):
            for j in range(6):
                K_global[GDL[i], GDL[j]] += Ke[i + 1, j + 1]

    return K_global

def solve_fem_numeric(K_global, F_global, fixed_dofs):
    """
    Resolve o sistema linear FEM:
        K_global * U = F_global
    aplicando condições de contorno e retornando deslocamentos e reações.
    
    Parâmetros:
    -----------
    K_global : np.ndarray
        Matriz de rigidez global [n_dof x n_dof]
    F_global : np.ndarray
        Vetor global de forças [n_dof]
    fixed_dofs : list[int]
        Índices dos graus de liberdade com deslocamento fixo (apoios)
    
    Retorna:
    --------
    U_full : np.ndarray
        Vetor completo de deslocamentos (livres e fixos)
    R : np.ndarray
        Vetor de reações nos apoios
    """
    total_dof = K_global.shape[0]
    
    # 1️ Determina graus de liberdade livres
    free_dofs = [i for i in range(total_dof) if i not in fixed_dofs]
    
    # 2️ Cria partições
    K_rr = K_global[np.ix_(free_dofs, free_dofs)]
    K_rf = K_global[np.ix_(free_dofs, fixed_dofs)]
    F_r = F_global[free_dofs]
    
    # 3️ Deslocamentos fixos (geralmente 0)
    U_f = np.zeros(len(fixed_dofs))
    
    # 4️ Resolve o sistema reduzido
    U_r = np.linalg.solve(K_rr, F_r - K_rf @ U_f)
    
    # 5️ Reconstrói o vetor completo de deslocamentos
    U_full = np.zeros(total_dof)
    U_full[free_dofs] = U_r
    U_full[fixed_dofs] = U_f
    
    # 6️ Calcula as reações (forças de apoio)
    R = K_global @ U_full - F_global
    
    return U_full, R

def fem(supports, concentrated_forces, distributed_loads, section_params):
    """
    Executa toda a análise estrutural por Elementos Finitos (viga 2D).

    Parâmetros:
    -----------
    supports : list[[x, tipo]]
        Lista de apoios. Tipos aceitos: 'fix', 'pin', 'mov'
    concentrated_forces : list[[x, Fy]]
        Lista de forças concentradas aplicadas (positivas para baixo).
    distributed_loads : list[[x_start, q_start, x_end, q_end]]
        Lista de carregamentos distribuídos lineares.
    section_params : list[[x_start, x_end, I, E, A, theta_deg]]
        Lista de propriedades das seções.

    Retorna:
    --------
    U_full : np.ndarray
        Vetor completo de deslocamentos e rotações.
    R : np.ndarray
        Vetor de reações (em todos os graus de liberdade).
    """
    # 1️ Construir lista de nós (coordenadas únicas)
    # NOTA: O recalculo dos nós a cada passo (baseado nas forces) é o
    # motivo pelo qual o FEM precisa ser refeito a cada passo.
    nodes_x = build_nodes_from_inputs(supports, concentrated_forces, section_params)
    
    # 2️ Criar estrutura de pontos e incógnitas
    points = add_points_from_inputs(
        supports, concentrated_forces, nodes_x
    )

    # 3️ Aplicar carregamentos distribuídos
    points = apply_distributed_loads_bulk(points, distributed_loads)

    # 4️ Extrair vetores F (forças) e U (deslocamentos)
    F, U = boundary_conditions(points)

    # 5️ Gerar elementos e número total de graus de liberdade
    elements, total_dof = elements_generator_with_sections(points, section_params)

    # 6️ Calcular matrizes de rigidez de cada elemento
    K_elements = []
    for el in elements:
        I, E, A, L, theta, *dofs = el
        Ke_global = numeric_element_stiffness(I, E, A, L, theta)

        # empacotar: 1ª linha = índices globais
        Ke_packed = np.zeros((7, 7))
        Ke_packed[0, 1:] = dofs
        Ke_packed[1:, 0] = dofs
        Ke_packed[1:, 1:] = Ke_global

        K_elements.append(Ke_packed)

    # 7️ Montar matriz de rigidez global
    K_global = assemble_global_stiffness(K_elements, total_dof)

    # 8️ Identificar graus de liberdade fixos (deslocamentos = 0)
    fixed_dofs = [i for i, val in enumerate(U) if val == 0]

    # 9️ Converter vetor de forças F em numérico (somar tuplas, ignorar símbolos)
    def extract_numeric_force(f):
        if isinstance(f, (int, float)):
            return float(f)
        elif isinstance(f, tuple):
            return sum(v for v in f if isinstance(v, (int, float, float)))
        else:
            return 0.0

    F_numeric = np.array([extract_numeric_force(f) for f in F], dtype=float)

    #  Resolver o sistema
    U_full, R = solve_fem_numeric(K_global, F_numeric, fixed_dofs)

    return U_full, R, nodes_x

def plot_graph_dict(data_dict, moment=False):
    """
    Plota o diagrama de esforço (cortante ou momento) a partir de um dicionário.

    Parâmetros
    ----------
    data_dict : dict
        {x_key: valor} onde x_key pode ter sufixos 'e' ou 'd' (descontinuidades)
    moment : bool, opcional
        Se True, plota o diagrama de Momento Fletor (invertendo o eixo Y)
        Se False, plota o diagrama de Cortante
    """
    import matplotlib.pyplot as plt
    import numpy as np

    # --- Função para ordenar chaves com sufixos ---
    def key_base_and_suffix(k):
        ks = str(k)
        if len(ks) > 0 and ks[-1] in ('e', 'd'):
            suffix = ks[-1]
            base_str = ks[:-1]
            try:
                base = float(base_str)
            except:
                base = float('inf')
            prio = 0 if suffix == 'e' else 1
            return base, prio
        else:
            try:
                base = float(ks)
            except:
                base = float('inf')
            return base, 2

    # --- Ordenar chaves do dicionário ---
    sorted_keys = sorted(data_dict.keys(), key=lambda k: key_base_and_suffix(k))

    # --- Extrair coordenadas e valores ---
    X = []
    Y = []
    for k in sorted_keys:
        base, _ = key_base_and_suffix(k)
        X.append(base)
        Y.append(float(data_dict[k]))

    X = np.array(X)
    Y = np.array(Y)

    # --- Título e unidades ---
    if moment:
        title = "Diagrama de Momento Fletor"
        ylabel = "Momento (kN·m)"
        unit = "kN·m"
    else:
        title = "Diagrama de Esforço Cortante"
        ylabel = "Cortante (kN)"
        unit = "kN"

    # --- Plotagem ---
    plt.figure(figsize=(12, 7))
    plt.plot(X, Y, color='blue', linewidth=2, label='Diagrama')
    plt.fill_between(X, Y, 0, color='lightgray', alpha=0.3)

    # --- Valores extremos ---
    global_max = np.max(Y)
    global_min = np.min(Y)
    global_max_coord = X[np.argmax(Y)]
    global_min_coord = X[np.argmin(Y)]

    plt.scatter(global_max_coord, global_max, color='green', s=100, zorder=5,
                label=f'Máx: {global_max:.3f} {unit}')
    plt.scatter(global_min_coord, global_min, color='red', s=100, zorder=5,
                label=f'Mín: {global_min:.3f} {unit}')

    plt.axhline(0, color='black', linestyle='-', linewidth=1, alpha=0.7)
    plt.axhline(global_max, color='green', linestyle='--', alpha=0.5)
    plt.axhline(global_min, color='red', linestyle='--', alpha=0.5)

    plt.title(title, fontsize=14, fontweight='bold')
    plt.xlabel("Posição (m)", fontsize=12)
    plt.ylabel(ylabel, fontsize=12)
    plt.grid(True, alpha=0.3)
    if moment:
        plt.gca().invert_yaxis()
    plt.legend(fontsize=11, loc='best', framealpha=0.9)
    plt.tight_layout()
    plt.show()

def sift_results(R, nodes_x, supports, concentrated_forces, tol=1e-6):
    """
    Filtra e separa as forças verticais (Fy) e as reações de apoio.
    As reações já vêm puras do FEM (sem incluir forças concentradas),
    então as forças aplicadas são somadas apenas ao dicionário forces_y.

    Parâmetros:
    -----------
    R : list or np.ndarray
        Vetor de reações nodais globais [Fx1, Fy1, M1, Fx2, Fy2, M2, ...].
    nodes_x : list[float]
        Coordenadas x de cada nó, na mesma ordem de R.
    supports : list[tuple]
        Lista de apoios [(x_coord, tipo_apoio), ...].
    concentrated_forces : list[tuple]
        Lista de forças concentradas [(x_coord, valor_força_y), ...].
    tol : float, opcional
        Tolerância para considerar forças muito pequenas como zero.
    
    Retorna:
    --------
    forces_y : dict
        Todas as forças verticais (Fy) associadas a cada coordenada x
        (reação + forças aplicadas).
    reaction_forces_y : dict
        Apenas as reações verticais puras nos apoios (Fy sem somar forças aplicadas).
    """

    # Extrair todas as forças verticais (Fy)
    forces_y = {
        x: R[3*i + 1] if abs(R[3*i + 1]) > tol else 0.0
        for i, x in enumerate(nodes_x)
    }

    # Coordenadas dos apoios
    coords_supports = {s[0] for s in supports}

    # Reações verticais puras (apenas nos apoios)
    reaction_forces_y = {x: fy for x, fy in forces_y.items() if x in coords_supports}

    # Somar forças concentradas no dicionário total (forces_y)
    for coord_x, force in concentrated_forces:
        if coord_x in forces_y:
            forces_y[coord_x] += force
        else:
            forces_y[coord_x] = force  # caso haja carga fora dos nós (raro, mas seguro)

    # Ordenar por coordenada
    forces_y = dict(sorted(forces_y.items()))
    reaction_forces_y = dict(sorted(reaction_forces_y.items()))

    return forces_y, reaction_forces_y

def calculate_shear_force(full_length, y_forces, distributed_loads, dx=1.0):
    """
    Calcula o diagrama de cortante (V) considerando forças pontuais e cargas distribuídas.

    full_length : float
        Comprimento total da viga (mm)
    y_forces : dict {x: Fy_em_N}
        Forças verticais aplicadas (positivas para cima)
    distributed_loads : list [[x_start, q_start, x_end, q_end]]
        Cargas distribuídas (N/unidade)
    dx : float
        Passo de integração (mm)

    Retorna:
    --------
    shear_dict : dict
        Dicionário com chaves 'x', 'xe' e 'xd' -> {coord: V_kN}
    """

    x_values = np.arange(0, full_length + dx, dx)
    n = len(x_values)

    # --- Calcular q(x) vetorizado em todo domínio ---
    q_total = np.zeros_like(x_values)
    for x_start, q_start, x_end, q_end in distributed_loads:
        in_range = (x_values >= x_start) & (x_values <= x_end)
        if x_end == x_start:
            q_interp = q_start * np.ones_like(x_values)
        else:
            t = (x_values - x_start) / (x_end - x_start)
            q_interp = (1 - t) * q_start + t * q_end
        q_total += np.where(in_range, q_interp, 0.0)

    # --- Converter q(x) em incrementos de cortante (kN) ---
    delta_v = (q_total[:-1] * dx) / 1000.0
    v_values = np.concatenate([[0.0], np.cumsum(delta_v)])  # acumulação contínua

    shear_dict = {}
    v = 0.0

    # --- Loop leve apenas para aplicar saltos concentrados ---
    # Coordenadas x arredondadas onde as forças y estão
    y_force_coords_rounded = {round(x, 6): fy for x, fy in y_forces.items()}
    
    for i, x in enumerate(x_values):
        x_round = round(x, 6)
        x_key_str = f"{x:.3f}" # Chave base

        # Adiciona o valor *antes* de qualquer salto
        shear_dict[x_key_str] = v_values[i]

        if x_round in y_force_coords_rounded:
            # Ponto de descontinuidade
            shear_dict[f"{x_key_str}e"] = v_values[i] # Valor à esquerda (before)
            
            Fy_kN = y_force_coords_rounded[x_round] / 1000.0
            v_values[i:] += Fy_kN  # soma o salto a partir daqui
            
            shear_dict[f"{x_key_str}d"] = v_values[i] # Valor à direita (after)
            # Remove a chave base duplicada se houver 'e' e 'd'
            if f"{x_key_str}e" in shear_dict:
                 del shear_dict[x_key_str]
            
            # Remove a força para não ser processada novamente se o dx for pequeno
            del y_force_coords_rounded[x_round] 
            
    return shear_dict


def calculate_shear_force(full_length, y_forces, distributed_loads, dx=1.0):
    """
    Calcula o diagrama de cortante (V) considerando forÃ§as pontuais e cargas distribuÃ­das.

    Esta redefiniÃ§Ã£o preserva a API original, mas garante que apoios,
    cargas concentradas e bordas de carregamentos distribuÃ­dos sejam
    sempre incluÃ­dos na malha de integraÃ§Ã£o, mesmo quando nÃ£o coincidem
    com o passo ``dx``.
    """

    x_regular = np.arange(0.0, full_length + dx, dx, dtype=float)
    x_breaks = [0.0, float(full_length)]
    x_breaks.extend(float(x) for x in y_forces.keys())
    for x_start, _, x_end, _ in distributed_loads:
        x_breaks.extend([float(x_start), float(x_end)])

    x_values = np.unique(np.round(np.concatenate([x_regular, x_breaks]), 6))
    x_values = x_values[(x_values >= -1e-6) & (x_values <= full_length + 1e-6)]
    if len(x_values) == 0:
        return {}
    x_values[0] = 0.0
    x_values[-1] = float(full_length)

    q_total = np.zeros_like(x_values, dtype=float)
    for x_start, q_start, x_end, q_end in distributed_loads:
        x0 = float(min(x_start, x_end))
        x1 = float(max(x_start, x_end))
        if abs(x1 - x0) <= 1e-12:
            continue

        in_range = (x_values >= x0 - 1e-9) & (x_values <= x1 + 1e-9)
        t = (x_values[in_range] - x_start) / (x_end - x_start)
        q_interp = (1.0 - t) * float(q_start) + t * float(q_end)
        q_total[in_range] += q_interp

    dx_values = np.diff(x_values)
    delta_v = 0.5 * (q_total[:-1] + q_total[1:]) * dx_values / 1000.0
    v_values = np.concatenate([[0.0], np.cumsum(delta_v)])

    shear_dict = {}
    y_force_coords = {round(float(x), 6): float(fy) for x, fy in y_forces.items()}

    for i, x in enumerate(x_values):
        x_round = round(float(x), 6)
        x_key_str = f"{x:.3f}"

        shear_dict[x_key_str] = v_values[i]

        if x_round in y_force_coords:
            shear_dict[f"{x_key_str}e"] = v_values[i]

            Fy_kN = y_force_coords[x_round] / 1000.0
            v_values[i:] += Fy_kN

            shear_dict[f"{x_key_str}d"] = v_values[i]
            shear_dict.pop(x_key_str, None)
            del y_force_coords[x_round]

    return shear_dict

def calculate_bending_moment_from_shear_fast(shear_dict):
    """
    Calcula o diagrama de momento fletor (M) a partir do diagrama de cortante (V),
    usando integração numérica vetorizada (regra dos trapézios cumulativa).
    """

    # Converter chaves e valores em arrays numéricos
    X = np.array([float(k.rstrip('ed')) for k in shear_dict.keys()])
    V = np.array(list(shear_dict.values()))

    # Ordenar por X
    sort_idx = np.argsort(X)
    X = X[sort_idx]
    V = V[sort_idx]

    # Integração vetorizada (área acumulada sob V(x))
    M = cumtrapz(V, X, initial=0)/1000  # resultado em kN·m

    # Criar dicionário {x: M}
    moment_dict = {f"{x:.3f}": m for x, m in zip(X, M)}

    return moment_dict

# =============================================================================
# NOVAS FUNÇÕES: LINHAS DE INFLUÊNCIA
# =============================================================================
def run_single_step_unit_load(x_load: float,
                              P_unit: float,
                              L_struct_mm: float,
                              supports: list,
                              section_params: list,
                              dx_diagrama: float = 1.0):
    """
    Função 'Worker' (para paralelização) que calcula os diagramas de esforço
    E AS REAÇÕES (em kN) para uma ÚNICA CARGA UNITÁRIA (P_unit) aplicada 
    em 'x_load'.
    
    RETORNA:
    shear (kN), moment (kN.m), labeled_reactions (kN)
    """
    try:
        # 1) Definir carregamentos (apenas uma carga concentrada)
        conc = [[x_load, P_unit]]
        dist = []

        # 2) Resolver via FEM
        U, R, x_nodes = fem(supports, conc, dist, section_params)

        # 3) Extrair forças internas (y_forces agora conterá reações + P_unit)
        #    reactions_y ainda estará em Newtons (N) aqui.
        forces_y, reactions_y = sift_results(R, x_nodes, supports, conc)
        
        # 4) Calcular diagramas completos (estes já convertem para kN e kN.m)
        shear = calculate_shear_force(L_struct_mm, forces_y, dist, dx=dx_diagrama) 
        moment = calculate_bending_moment_from_shear_fast(shear)

        # 5) --- AJUSTE: Rotular reações e converter para kN ---
        # Garante que os apoios 'A', 'B', 'C' sempre sigam a ordem da coordenada X
        sorted_support_coords = sorted([float(s[0]) for s in supports])
        
        labeled_reactions = {}
        for i, x_coord in enumerate(sorted_support_coords):
            label = chr(65 + i) # 65 é o char 'A'
            # Pega a reação (em N) e divide por 1000.0 para salvar em kN
            labeled_reactions[label] = reactions_y.get(x_coord, 0.0) / 1000.0

        # Retorna os 3 resultados (agora todos em kN ou kN.m)
        return shear, moment, labeled_reactions
    
    except Exception as e:
        print(f"Erro ao processar carga unitária em x={x_load}: {e}")
        # Retorna None para os 3
        return None, None, None

def calculate_influence_diagrams(L_struct_mm: float,
                                 P_unit: float,
                                 supports: list,
                                 section_params: list,
                                 step_mm: float = 100.0,
                                 diagram_dx: float = 1.0):
    """
    Executa a simulação paralela da carga unitária móvel.
    
    Retorna:
    --------
    all_shear_diagrams : dict
        {x_load_1: shear_dict_1, ...}
    all_moment_diagrams : dict
        {x_load_1: moment_dict_1, ...}
    all_reaction_diagrams : dict
        {x_load_1: {'A': R_A, 'B': R_B, ...}, ...}
    """
    print("Iniciando cálculo paralelo para Linhas de Influência...")
    
    all_shear_diagrams = {}
    all_moment_diagrams = {}
    all_reaction_diagrams = {} # <-- NOVO DICIONÁRIO

    # A carga unitária "passeia" de 0 até o fim da estrutura
    positions = list(np.arange(0, L_struct_mm + step_mm, step_mm))
    
    n_steps = len(positions)
    print(f"Total de {n_steps} posições da carga unitária a simular.")

    num_workers = multiprocessing.cpu_count()
    print(f"Utilizando {num_workers} núcleos de processamento...")

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(run_single_step_unit_load, 
                            x, P_unit, L_struct_mm, 
                            supports, section_params, diagram_dx): x
            for x in positions
        }

        completed_count = 0
        print_interval = max(1, n_steps // 20)
        
        for future in as_completed(futures):
            x_load = futures[future] # Posição da carga
            try:
                # Desempacota os 3 resultados
                shear, moment, reactions = future.result()
                
                if shear is not None:
                    # Armazena o diagrama completo, usando a posição da carga como chave
                    all_shear_diagrams[x_load] = shear
                    all_moment_diagrams[x_load] = moment
                    all_reaction_diagrams[x_load] = reactions # <-- ARMAZENA REAÇÕES
                
                completed_count += 1
                if completed_count % print_interval == 0 or completed_count == n_steps:
                     print(f"Progresso (LI): {completed_count}/{n_steps} ({int(100.0 * completed_count / n_steps)}%)")
            
            except Exception as exc:
                print(f'Posição da carga x={x_load} gerou uma exceção: {exc}')
    
    print("Cálculo de todos os diagramas de influência concluído.")
    # Retorna os 3 dicionários
    return all_shear_diagrams, all_moment_diagrams, all_reaction_diagrams

def plot_influence_line(li_dict, title, ylabel="Influência (Adimensional)", invert_y: bool = False):
    """
    Plota um gráfico simples de Linha de Influência (1D).
    
    Parâmetros:
    -----------
    li_dict : dict
        Dicionário {x_load: value}
    title : str
        Título do gráfico
    ylabel : str
        Rótulo do eixo Y
    invert_y : bool, opcional
        Se True, inverte o eixo Y (convenção para momentos). Padrão é False.
    """
    
    if not li_dict:
        print(f"Dicionário da Linha de Influência está vazio. Não é possível plotar '{title}'.")
        return

    # Ordena os dados por x_load
    X = np.array(sorted(li_dict.keys()))
    Y = np.array([li_dict[x] for x in X])

    plt.figure(figsize=(12, 7))
    plt.plot(X, Y, color='purple', linewidth=2, label='Linha de Influência')
    plt.fill_between(X, Y, 0, color='purple', alpha=0.1)

    # --- Valores extremos ---
    global_max = np.max(Y)
    global_min = np.min(Y)
    global_max_coord = X[np.argmax(Y)]
    global_min_coord = X[np.argmin(Y)]

    plt.scatter(global_max_coord, global_max, color='green', s=100, zorder=5,
                label=f'Máx: {global_max:.3f}')
    plt.scatter(global_min_coord, global_min, color='red', s=100, zorder=5,
                label=f'Mín: {global_min:.3f}')
    
    plt.axhline(0, color='black', linestyle='-', linewidth=1, alpha=0.7)
    plt.axhline(global_max, color='green', linestyle='--', alpha=0.5)
    plt.axhline(global_min, color='red', linestyle='--', alpha=0.5)

    plt.title(title, fontsize=14, fontweight='bold')
    plt.xlabel("Posição da Carga Unitária (mm)", fontsize=12)
    plt.ylabel(ylabel, fontsize=12)
    plt.grid(True, alpha=0.3)
    
    # --- Modificação Chave ---
    if invert_y:
        plt.gca().invert_yaxis()
        
    plt.legend(fontsize=11, loc='best', framealpha=0.9)
    plt.tight_layout()
    plt.show()

def extract_influence_line(all_diagrams: dict,
                           k_mm: float,
                           diagram_type: str = 'moment',
                           side: str = 'e'):
    """
    Extrai a Linha de Influência para um ponto k_mm específico
    a partir do dicionário 'all_diagrams' (gerado pela função anterior).

    Parâmetros:
    -----------
    all_diagrams : dict
        O "super-dicionário" {x_load: diagram_dict, ...}
    k_mm : float
        A coordenada 'x' do ponto de interesse (ex: 5000.0)
    diagram_type : str
        'moment' ou 'shear'
    side : str
        'e' (esquerda) ou 'd' (direita). Relevante apenas para 'shear'.
    
    Retorna:
    --------
    li_dict : dict
        A Linha de Influência: {x_load: effort_at_k, ...}
    """
    
    li_dict = {}
    
    # Define a chave que procuraremos dentro de cada diagrama
    k_key_str = f"{k_mm:.3f}"
    k_key_to_find = ""
    
    if diagram_type == 'moment':
        k_key_to_find = k_key_str
    elif diagram_type == 'shear':
        k_key_to_find = f"{k_key_str}{side}" # ex: "5000.000e"
    else:
        raise ValueError("diagram_type deve ser 'moment' ou 'shear'")
    
    print(f"Extraindo LI para o ponto k={k_mm} (Chave: '{k_key_to_find}')")
    
    # Ordena pela posição da carga (x_load)
    sorted_x_loads = sorted(all_diagrams.keys())
    
    warnings = 0
    for x_load in sorted_x_loads:
        diagram = all_diagrams[x_load]
        value = 0.0
        
        if diagram:
            # Procura o valor no ponto k
            value = diagram.get(k_key_to_find)
            
            # Fallback (importante!)
            # Se for momento, 'k_key_to_find' é "5000.000"
            # Se for cortante, 'k_key_to_find' é "5000.000e"
            # Se o ponto k não tiver descontinuidade, a chave 'e'/'d' pode não
            # existir, então tentamos a chave base.
            if value is None:
                value = diagram.get(k_key_str, 0.0) # Tenta a chave base
                if warnings < 5: # Limita o número de avisos
                    #print(f"Aviso: Chave '{k_key_to_find}' não encontrada (x_load={x_load}). Usando chave base '{k_key_str}'.")
                    warnings += 1

        li_dict[x_load] = float(value)
        
    return li_dict

def extract_influence_line_r_apoio(all_reaction_diagrams: dict,
                                   apoio_label: str):
    """
    Extrai a Linha de Influência para uma REAÇÃO DE APOIO específica.

    Parâmetros:
    -----------
    all_reaction_diagrams : dict
        O "super-dicionário" {x_load: { 'A': R_A, 'B': R_B, ... }, ...}
    apoio_label : str
        O rótulo do apoio (ex: "A", "B", "C"). Não é case-sensitive.
    
    Retorna:
    --------
    li_dict : dict
        A Linha de Influência da Reação: {x_load: reaction_at_label, ...}
    """
    
    li_dict = {}
    apoio_label_upper = apoio_label.upper() # Garante A, B, C

    print(f"Extraindo LI para a Reação do Apoio '{apoio_label_upper}'")
    
    # Ordena pela posição da carga (x_load)
    sorted_x_loads = sorted(all_reaction_diagrams.keys())
    
    for x_load in sorted_x_loads:
        # Pega o dicionário de reações para esta posição da carga
        reaction_dict = all_reaction_diagrams.get(x_load)
        value = 0.0
        
        if reaction_dict:
            # Busca o valor da reação para o apoio_label
            value = reaction_dict.get(apoio_label_upper, 0.0)

        li_dict[x_load] = float(value)
        
    return li_dict

def calculate_train_envelope_on_li(
    li_dict: dict,
    P: float,
    q_train: float,
    q_train_ext: float,
    train_length_mm: float = 6000.0,
    axle_offsets_mm: list | None = None,
    step_mm: float = 100.0
):
    """
    Calcula os esforços máximo e mínimo em um ponto k (definido por li_dict)
    causados pelo movimento do trem-tipo, considerando:

    - Eixos (P)
    - Carga distribuída dentro do trem (q_train)
    - Carga distribuída externa q_train_ext:
          • Máximo → aplica em regiões onde LI(x)>0 e fora do trem
          • Mínimo → aplica em regiões onde LI(x)<0 e fora do trem

    CORREÇÃO DE SINAL incluída (LI gerada para 1 kN para baixo).
    """

    if axle_offsets_mm is None:
        axle_offsets_mm = [1500.0, 3000.0, 4500.0]

    # Converter LI em arrays ordenados
    X_li = np.array(sorted(li_dict.keys()))
    Y_li = np.array([li_dict[x] for x in X_li])
    L_struct_mm = X_li[-1]

    # Função auxiliar: integra LI em um intervalo arbitrário
    def _integrate_segment(xa, xb):
        xa = max(xa, X_li[0])
        xb = min(xb, X_li[-1])
        if xb <= xa:
            return 0.0
        X_inside = X_li[(X_li >= xa) & (X_li <= xb)]
        if len(X_inside) == 0:
            # Somente extremos → interpolar
            X_seg = np.array([xa, xb])
        else:
            X_seg = np.concatenate(([xa], X_inside, [xb]))
        X_seg = np.unique(X_seg)
        Y_seg = np.interp(X_seg, X_li, Y_li)
        return np.trapezoid(Y_seg, X_seg)

    # Preparar laço do trem
    positions = np.arange(
        -train_length_mm,
        L_struct_mm + train_length_mm + step_mm,
        step_mm
    )

    max_effort = -np.inf
    min_effort = +np.inf
    x_max_effort = positions[0]
    x_min_effort = positions[0]

    for x_left in positions:

        # -------------------------
        # A) Efeito dos Eixos (P)
        # -------------------------
        E_axles = 0.0
        for offset in axle_offsets_mm:
            x_axle = x_left + offset
            if X_li[0] <= x_axle <= L_struct_mm:
                li_value = np.interp(x_axle, X_li, Y_li)
                E_axles += P * li_value

        # -----------------------------------------------
        # B) Efeito da carga distribuída dentro do trem
        # -----------------------------------------------
        x_q1, x_q2 = x_left, x_left + train_length_mm
        area_inside = _integrate_segment(x_q1, x_q2)
        E_dist_internal = q_train * area_inside

        # -------------------------------------------------------
        # C) Efeito da carga distribuída externa (q_train_ext)
        #     Agora com a regra correta:
        #     Máximo → usar regiões fora do trem onde LI>0
        #     Mínimo → usar regiões fora do trem onde LI<0
        # -------------------------------------------------------

        # Regiões externas:
        #   Região 1 = [0, x_left]
        #   Região 2 = [x_left + train_length, L_struct]
        ext_intervals = [
            (X_li[0], x_left),
            (x_left + train_length_mm, L_struct_mm)
        ]

        # --- POSITIVO (para esforço máximo)
        area_ext_pos = 0.0
        # --- NEGATIVO (para esforço mínimo)
        area_ext_neg = 0.0

        for xa, xb in ext_intervals:
            # criamos um grid refinado dentro do intervalo
            Xs = X_li[(X_li >= xa) & (X_li <= xb)]
            if len(Xs) == 0:
                continue
            Ys = np.interp(Xs, X_li, Y_li)

            # partes positivas (para máximo)
            Ypos = np.where(Ys > 0, Ys, 0)
            # partes negativas (para mínimo)
            Yneg = np.where(Ys < 0, Ys, 0)

            if len(Xs) > 1:
                area_ext_pos += np.trapezoid(Ypos, Xs)
                area_ext_neg += np.trapezoid(Yneg, Xs)

        # Cálculo dos efeitos:
        E_ext_for_max = q_train_ext * area_ext_pos
        E_ext_for_min = q_train_ext * area_ext_neg

        # ------------------------------
        # D) Soma total bruta
        # ------------------------------
        E_total_raw_max = E_axles + E_dist_internal + E_ext_for_max
        E_total_raw_min = E_axles + E_dist_internal + E_ext_for_min

        # ---------------------------------------------
        # E) Correção de sinal (LI feita com unidade ↓)
        # ---------------------------------------------
        E_total_corrected_max = -E_total_raw_max
        E_total_corrected_min = -E_total_raw_min

        # ------------------------------
        # F) Atualizar envoltórias
        # ------------------------------
        if E_total_corrected_max > max_effort:
            max_effort = E_total_corrected_max
            x_max_effort = x_left

        if E_total_corrected_min < min_effort:
            min_effort = E_total_corrected_min
            x_min_effort = x_left

    return (max_effort, x_max_effort), (min_effort, x_min_effort)

def calculate_full_moment_envelope(
    all_moment_diagrams: dict,
    L_struct_mm: float,
    dx: float = 50.0,
    # parâmetros do trem
    P: float = 0.0,
    q_train: float = 0.0,
    q_train_ext: float = 0.0,
    train_length_mm: float = 6000.0,
    axle_offsets_mm: list | None = None,
    train_step_mm: float = 100.0,
    include_positions: bool = False
):
    """
    Gera a envoltória de MOMENTO para todos os pontos k em [0, L].
    A cada k:
        - extrai a LI de MOMENTO (normal, sem lado e/d)
        - aplica o trem (calculate_train_envelope_on_li)
        - retorna max/min ou (max_tuple, min_tuple), dependendo do include_positions.
    """

    envelope = {}
    xs = np.arange(0.0, L_struct_mm + 1e-9, dx)

    for k in xs:
        # 1) Extract LI(M) no ponto k
        li_k = extract_influence_line(
            all_moment_diagrams,
            k_mm=float(k),
            diagram_type="moment"
        )

        # 2) Aplica o trem
        max_tuple, min_tuple = calculate_train_envelope_on_li(
            li_dict=li_k,
            P=P,
            q_train=q_train,
            q_train_ext=q_train_ext,
            train_length_mm=train_length_mm,
            axle_offsets_mm=axle_offsets_mm,
            step_mm=train_step_mm
        )

        # max_tuple = (max_val, x_left_max)
        # min_tuple = (min_val, x_left_min)

        if include_positions:
            envelope[float(k)] = (max_tuple, min_tuple)
        else:
            envelope[float(k)] = (float(max_tuple[0]), float(min_tuple[0]))

    return envelope

def calculate_full_shear_envelope(
    all_shear_diagrams: dict,
    L_struct_mm: float,
    dx: float = 50.0,
    # parâmetros do trem
    P: float = 0.0,
    q_train: float = 0.0,
    q_train_ext: float = 0.0,
    train_length_mm: float = 6000.0,
    axle_offsets_mm: list | None = None,
    train_step_mm: float = 100.0,
    include_positions: bool = False
):
    """
    Gera a envoltória correta de CORTANTE.
    
    Para cada k:
        1) extrai LI_e  (lado esquerdo)
        2) extrai LI_d  (lado direito)
        3) calcula envelope para LI_e
        4) calcula envelope para LI_d
        5) máximo governa = max(max_e, max_d)
        6) mínimo governa = min(min_e, min_d)

    Retorna dict { k : (max_val, min_val) } 
    Se include_positions=True, retorna também as posições x_left governantes.
    """

    envelope = {}
    xs = np.arange(0.0, L_struct_mm + 1e-9, dx)

    for k in xs:
        li_e, li_d = robust_extract_shear_sided(all_shear_diagrams, k, eps=0.0001)
        max_e, min_e = calculate_train_envelope_on_li(li_e, P=P, q_train=q_train,
                                                       q_train_ext=q_train_ext,
                                                       train_length_mm=train_length_mm,
                                                     axle_offsets_mm=axle_offsets_mm,
                                                       step_mm=train_step_mm)
        max_d, min_d = calculate_train_envelope_on_li(li_d, P=P, q_train=q_train, q_train_ext=q_train_ext, train_length_mm=train_length_mm, axle_offsets_mm=axle_offsets_mm, step_mm=train_step_mm)

        # Combina governantes
        if max_e[0] >= max_d[0]:
            max_governa = max_e
        else:
            max_governa = max_d

        if min_e[0] <= min_d[0]:
            min_governa = min_e
        else:
            min_governa = min_d

        if include_positions:
            envelope[float(k)] = (max_governa, min_governa)
        else:
            envelope[float(k)] = (float(max_governa[0]), float(min_governa[0]))

    return envelope

def robust_extract_shear_sided(all_shear_diagrams, k_mm, eps=1e-3):
    """
    Retorna dois dicts (li_e, li_d) extraídos de all_shear_diagrams
    de modo robusto evitando usar fallback que perde saltos.
    """
    # tenta extrair diretamente 'e' e 'd'
    li_e = extract_influence_line(all_shear_diagrams, k_mm=k_mm, diagram_type='shear', side='e')
    li_d = extract_influence_line(all_shear_diagrams, k_mm=k_mm, diagram_type='shear', side='d')

    # Se alguma das extrações usar fallback para a chave base (detectar por valores "suavizados"),
    # tentar extrair em k-eps e k+eps como backup:
    # (essa heurística ajuda quando o diagrama não tem e/d nas chaves exatas)
    if all(v == li_e[next(iter(li_e))] for v in li_e.values()):
        # li_e é constante → possivelmente fallback. tenta k - eps
        li_e = extract_influence_line(all_shear_diagrams, k_mm=(k_mm - eps), diagram_type='shear', side='e')
    if all(v == li_d[next(iter(li_d))] for v in li_d.values()):
        li_d = extract_influence_line(all_shear_diagrams, k_mm=(k_mm + eps), diagram_type='shear', side='d')

    return li_e, li_d

def plot_envelope(
    envelope_dict: dict,
    title: str = "Envoltória",
    ylabel: str = "Esforço",
    diagram_type: str = "moment",
    show_positions: bool = False,
    marker_every: int | None = None
):
    """
    Plota a envoltória a partir do dicionário retornado por
    calculate_full_envelope_from_all_diagrams.

    envelope_dict: { x : (max, min) }  ou  { x : ((max, x_left_max),(min,x_left_min)) }
    show_positions: se True e se o dicionário tiver posições, plota marcadores das posições x_left
    marker_every: se int, plota um marcador a cada 'marker_every' pontos (para não lotar o gráfico)
    """

    xs = np.array(sorted(envelope_dict.keys()))
    # detecta formato de valores
    sample = envelope_dict[xs[0]]
    has_positions = (isinstance(sample[0], (list, tuple)) and len(sample[0]) == 2)

    if has_positions:
        max_vals = np.array([envelope_dict[x][0][0] for x in xs])
        min_vals = np.array([envelope_dict[x][1][0] for x in xs])
        if show_positions:
            max_pos = np.array([envelope_dict[x][0][1] for x in xs])
            min_pos = np.array([envelope_dict[x][1][1] for x in xs])
    else:
        max_vals = np.array([envelope_dict[x][0] for x in xs])
        min_vals = np.array([envelope_dict[x][1] for x in xs])

    plt.figure(figsize=(12, 7))

    plt.plot(xs, max_vals, label="Envoltória Máxima", linewidth=2)
    plt.fill_between(xs, max_vals, 0, alpha=0.12)

    plt.plot(xs, min_vals, label="Envoltória Mínima", linewidth=2)
    plt.fill_between(xs, min_vals, 0, alpha=0.12)

    if diagram_type == "moment":
        plt.gca().invert_yaxis()

    # se pediram para mostrar posições x_left que geraram os extremos
    if show_positions and has_positions:
        # Opcional: reduzir quantidade de marcadores
        idxs = np.arange(len(xs))
        if isinstance(marker_every, int) and marker_every > 0:
            idxs = idxs[::marker_every]

        # plotar setas/markers para máximos e mínimos
        plt.scatter(xs[idxs], max_pos[idxs], marker="v", s=40, label="x_left (max)", zorder=5)
        plt.scatter(xs[idxs], min_pos[idxs], marker="^", s=40, label="x_left (min)", zorder=5)

    plt.title(title, fontsize=14, fontweight="bold")
    plt.xlabel("Posição ao longo da viga (mm)")
    plt.ylabel(ylabel)
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.show()

def refine_sections(section_params, dx_ref=50.0):
    """
    Quebra cada seção em sub-seções com passo dx_ref.
    Retorna novo section_params expandido.
    """
    refined = []
    for xs, xe, I, E, A, th in section_params:
        xs = float(xs); xe = float(xe)
        if xe <= xs:
            continue
        xs_local = np.arange(xs, xe, dx_ref)
        xs_local = list(xs_local) + [xe]
        for i in range(len(xs_local)-1):
            refined.append([xs_local[i], xs_local[i+1], I, E, A, th])
    return refined

def ensure_point_in_sections(section_params, x_point):
    """
    Garante que exista um nó exatamente em x_point dividindo a seção que o contém.
    Retorna section_params possivelmente alterado.
    """
    out = []
    x_point = float(x_point)
    for xs, xe, I, E, A, th in section_params:
        if xs < x_point < xe:
            # dividir
            out.append([xs, x_point, I, E, A, th])
            out.append([x_point, xe, I, E, A, th])
        else:
            out.append([xs, xe, I, E, A, th])
    return out

def build_K_and_nodes(supports, concentrated_forces, distributed_loads, section_params):
    """
    Recria o mesmo processo do fem() mas retorna K_global, F_numeric, fixed_dofs, nodes_x.
    """
    nodes_x = build_nodes_from_inputs(supports, concentrated_forces, section_params)
    points = add_points_from_inputs(supports, concentrated_forces, nodes_x)
    points = apply_distributed_loads_bulk(points, distributed_loads)
    F, U = boundary_conditions(points)
    elements, total_dof = elements_generator_with_sections(points, section_params)

    # montar K_elements (mesma lógica do fem)
    K_elements = []
    for el in elements:
        I, E, A, L, theta, *dofs = el
        Ke_global = numeric_element_stiffness(I, E, A, L, theta)
        Ke_packed = np.zeros((7, 7))
        Ke_packed[0, 1:] = dofs
        Ke_packed[1:, 0] = dofs
        Ke_packed[1:, 1:] = Ke_global
        K_elements.append(Ke_packed)

    K_global = assemble_global_stiffness(K_elements, total_dof)

    # fixed DOFs (onde U == 0)
    fixed_dofs = [i for i, val in enumerate(U) if val == 0]

    # Converter F para numérico
    def extract_numeric_force(f):
        if isinstance(f, (int, float)):
            return float(f)
        elif isinstance(f, tuple):
            return sum(v for v in f if isinstance(v, (int, float, float)))
        else:
            return 0.0
    F_numeric = np.array([extract_numeric_force(f) for f in F], dtype=float)

    return K_global, F_numeric, fixed_dofs, nodes_x, elements, total_dof

def LI_cortante_via_deslocamento(
    x_consulta: float,
    L_struct_mm: float,
    supports: list,
    section_params: list,
    distributed_loads: list | None = None,
    dx_ref: float = 50.0,
    diagram_dx: float = 1.0
):
    """
    Calcula LI de cortante usando deslocamento vertical unitário aplicado no DOF do nó em x_consulta.
    Retorna shear_dict pronto para plot.
    """
    # 1) Refinar seções para garantir nó
    sections = ensure_point_in_sections(section_params, x_consulta)
    sections = refine_sections(sections, dx_ref=dx_ref)

    # 2) Montar K_global e demais vetores usando a malha refinada (sem cargas externas)
    K_global, F_numeric, fixed_dofs, nodes_x, elements, total_dof = build_K_and_nodes(
        supports=supports,
        concentrated_forces=[],          # sem cargas reais
        distributed_loads=[],
        section_params=sections
    )

    # 3) Identificar DOF vertical correspondente ao nó em x_consulta
    # nodes_x são as coordenadas dos nós usados na montagem
    # cada nó tem 3 DOFs: [g1,g2,g3] conforme elements_generator_with_sections usa
    # convenção: nodo i (0-based) -> DOF indices [3*i, 3*i+1, 3*i+2]
    idx_node = np.argmin(np.abs(np.array(nodes_x) - float(x_consulta)))
    dof_vertical = idx_node * 3 + 1   # uy é o segundo dof local/ global (0-based)

    # 4) Montar prescrição U_f onde apenas esse dof tem desloc = 1.0
    total_dof = K_global.shape[0]
    U_full = np.zeros(total_dof)
    prescribed = {dof_vertical: 1.0}

    # 5) Resolver por particionamento (sem forças externas)
    all_dofs = list(range(total_dof))
    fixed = sorted(fixed_dofs)
    # Aqui "prescribed" são deslocamentos específicos (não os apoios). Precisamos tratar:
    # vamos considerar os apoios como fixos (fixed_dofs) e adicionar o dof_vertical
    # como "prescrito" (remoção do conjunto livre).
    presc_dofs = list(prescribed.keys())
    # União de apoios + prescritos
    constrained = sorted(set(fixed + presc_dofs))
    free = [i for i in all_dofs if i not in constrained]

    K_ff = K_global[np.ix_(free, free)]
    K_fc = K_global[np.ix_(free, constrained)]
    K_cf = K_global[np.ix_(constrained, free)]
    K_cc = K_global[np.ix_(constrained, constrained)]

    # Vetores
    F_f = np.zeros(len(free))
    U_c = np.zeros(len(constrained))
    # preencher U_c com os valores prescritos (apoios = 0; prescritos dof_vertical = 1)
    # construir mapping constrained_index -> dof
    for i, dof in enumerate(constrained):
        if dof in prescribed:
            U_c[i] = prescribed[dof]
        else:
            U_c[i] = 0.0

    # resolver K_ff * U_f = - K_fc * U_c  (já que F_f = 0)
    if K_ff.size == 0:
        U_f = np.array([])
    else:
        U_f = np.linalg.solve(K_ff, -K_fc @ U_c)

    # reconstruir U_full
    U_full = np.zeros(total_dof)
    U_full[free] = U_f
    U_full[constrained] = U_c

    # 6) Reações: R = K_global @ U_full  (nenhuma força aplicada)
    R = K_global @ U_full

    # 7) Extrair forças nodais verticais (R já em N)
    forces_y = {x: R[3*i + 1] for i, x in enumerate(nodes_x)}

    # 8) Montar diagrama de cortante (divide por 1000 dentro)
    shear_dict = calculate_shear_force(L_struct_mm, forces_y, [], dx=diagram_dx)

    return shear_dict

def LI_cortante_via_deslocamento_descontinuo(
    x_consulta: float,
    L_struct_mm: float,
    supports: list,
    section_params: list,
    distributed_loads: list | None = None,
    dx_ref: float = 50.0,
    sinal_inverso: bool = True,
    tol: float = 1e-6
) -> dict:
    """
    Calcula a Linha de Influência (LI) para o esforço cortante V em x_consulta,
    usando deslocamento unitário descontínuo (salto em v na seção).

    Retorna:
        li_dict: dict {x: valor_LI} — pode ser plotado diretamente com plot_graph_dict(li_dict, moment=False)

    Nota: Sem cargas externas (distributed_loads é ignorado para LI, mas mantido para compatibilidade).
    """
    if distributed_loads is None:
        distributed_loads = []

    # 1) Refinar seções para garantir precisão na LI
    sections = refine_sections(section_params, dx_ref=dx_ref)

    # 2) Gerar nós iniciais (sem duplicação ainda)
    nodes_x = build_nodes_from_inputs(supports, [], sections)  # Sem forças concentradas para LI
    nodes_x = sorted(set(nodes_x))  # Garantir únicos e ordenados

    # 3) Duplicar o nó em x_consulta (criar left e right na mesma x)
    idx_consulta = -1
    for i, x in enumerate(nodes_x):
        if abs(x - x_consulta) < tol:
            idx_consulta = i
            break
    if idx_consulta == -1:
        # Se não existir, adicionar e reordenar
        nodes_x.append(x_consulta)
        nodes_x = sorted(set(nodes_x))
        idx_consulta = nodes_x.index(x_consulta)

    # Criar lista de pontos com duplicação
    points = []
    node_id = 0  # ID global para nós (usado para DOFs)
    for i, x in enumerate(nodes_x):
        if i == idx_consulta:
            # Duplicar: nó left e right
            points.append([x, f'Fx{node_id+1}', f'Fy{node_id+1}', f'M{node_id+1}', f'u{node_id+1}', f'v{node_id+1}', f'rot{node_id+1}'])  # left
            node_id += 1
            points.append([x, f'Fx{node_id+1}', f'Fy{node_id+1}', f'M{node_id+1}', f'u{node_id+1}', f'v{node_id+1}', f'rot{node_id+1}'])  # right
            node_id += 1
        else:
            points.append([x, f'Fx{node_id+1}', f'Fy{node_id+1}', f'M{node_id+1}', f'u{node_id+1}', f'v{node_id+1}', f'rot{node_id+1}'])
            node_id += 1

    # Ajustar apoios e condições (aplicar apoios originais aos nós não-duplicados)
    points = add_points_from_inputs(supports, [], [p[0] for p in points])  # Sem forças concentradas
    points = apply_distributed_loads_bulk(points, distributed_loads)  # Se houver, mas para LI puro, ignore

    # 4) Gerar elementos com ajuste para duplicação
    n_nodes = len(points)
    elements = []
    for elem_id in range(n_nodes - 1):
        x_left = points[elem_id][0]
        x_right = points[elem_id + 1][0]
        L_elem = x_right - x_left
        if L_elem <= tol:  # Pular elementos de comprimento zero (descontinuidade)
            continue

        # Encontrar seção correspondente (usando midpoint)
        x_mid = 0.5 * (x_left + x_right)
        matched = None
        for xs, xe, I, E, A, theta in sections:
            if min(xs, xe) <= x_mid <= max(xs, xe):
                matched = (float(I), float(E), float(A), float(theta))
                break
        if matched is None:
            raise ValueError(f"Sem seção para midpoint {x_mid}")

        I_, E_, A_, theta_ = matched

        # DOFs: sequencial por nó (node_id 0-based = elem_id for left? Não, sempre sequencial)
        gdl_start = elem_id * 3 + 1
        gdl_end = gdl_start + 5
        dofs = list(range(gdl_start, gdl_end + 1))

        element = [I_, E_, A_, L_elem, theta_, *dofs]
        elements.append(element)

    total_dof = n_nodes * 3

    # 5) Montar K_global
    K_elements = []
    for el in elements:
        I, E, A, L, theta, *dofs = el
        Ke_global = numeric_element_stiffness(I, E, A, L, theta)
        Ke_packed = np.zeros((7, 7))
        Ke_packed[0, 1:] = dofs
        Ke_packed[1:, 0] = dofs
        Ke_packed[1:, 1:] = Ke_global
        K_elements.append(Ke_packed)

    K_global = assemble_global_stiffness(K_elements, total_dof)

    # 6) Adicionar penalty para continuidade em u e rot (mas não em v)
    alpha = 1e12 * np.max(np.abs(K_global)) if np.max(np.abs(K_global)) > 0 else 1e12
    idx_left = idx_consulta
    idx_right = idx_consulta + 1  # Ajustado pela duplicação

    # DOFs (0-based)
    dof_u_l = 3 * idx_left
    dof_u_r = 3 * idx_right
    dof_rot_l = 3 * idx_left + 2
    dof_rot_r = 3 * idx_right + 2

    # Penalty para u_l = u_r
    K_global[dof_u_l, dof_u_l] += alpha
    K_global[dof_u_r, dof_u_r] += alpha
    K_global[dof_u_l, dof_u_r] -= alpha
    K_global[dof_u_r, dof_u_l] -= alpha

    # Penalty para rot_l = rot_r
    K_global[dof_rot_l, dof_rot_l] += alpha
    K_global[dof_rot_r, dof_rot_r] += alpha
    K_global[dof_rot_l, dof_rot_r] -= alpha
    K_global[dof_rot_r, dof_rot_l] -= alpha

    # 7) Extrair U e identificar fixed_dofs (apoios)
    F, U = boundary_conditions(points)
    fixed_dofs = [i for i, val in enumerate(U) if val == 0]  # Apoios fixos

    # Prescrever deslocamento descontínuo: salto unitário centrado
    dof_v_l = 3 * idx_left + 1
    dof_v_r = 3 * idx_right + 1
    prescribed = {dof_v_l: -0.5, dof_v_r: 0.5}  # Salto total =1

    # Resolver com prescrições
    all_dofs = list(range(total_dof))
    constrained = sorted(set(fixed_dofs) | set(prescribed.keys()))
    free = [i for i in all_dofs if i not in constrained]

    K_ff = K_global[np.ix_(free, free)]
    K_fc = K_global[np.ix_(free, constrained)]
    U_c = np.zeros(len(constrained))
    for i, dof in enumerate(constrained):
        U_c[i] = prescribed.get(dof, 0.0)  # Prescritos ou 0 para apoios

    # Resolver: K_ff * U_f = -K_fc * U_c (F_f = 0)
    if K_ff.size > 0:
        U_f = np.linalg.solve(K_ff, -K_fc @ U_c)
    else:
        U_f = np.array([])

    U_full = np.zeros(total_dof)
    U_full[free] = U_f
    U_full[constrained] = U_c

    # 8) Calcular reações R = K @ U (F=0)
    R = K_global @ U_full

    # 9) Calcular Q_unit_jump (virtual shear para salto unitário)
    r_left = R[dof_v_l]
    r_right = R[dof_v_r]
    Q_unit_jump = - r_left  # Convenção: shear virtual (ajuste se sinal errado; altern: ( - r_left - r_right ) / 2 )

    # 10) Extrair LI: v(x) / Q_unit_jump
    li_dict = {}
    current_idx = 0
    for orig_x in nodes_x:
        if abs(orig_x - x_consulta) < tol:
            # Duplicado
            v_left = U_full[3 * current_idx + 1] / Q_unit_jump
            current_idx += 1
            v_right = U_full[3 * current_idx + 1] / Q_unit_jump
            current_idx += 1
            key_base = f"{orig_x:.3f}"
            li_dict[f"{key_base}e"] = v_left
            li_dict[f"{key_base}d"] = v_right
        else:
            v = U_full[3 * current_idx + 1] / Q_unit_jump
            li_dict[f"{orig_x:.3f}"] = v
            current_idx += 1

    # 11) Ajustar sinal (se necessário)
    if sinal_inverso:
        for key in li_dict:
            li_dict[key] = -li_dict[key]

    return li_dict

