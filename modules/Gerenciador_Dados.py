# ============================================================================
# GERENCIADOR_DADOS.PY - Gerenciamento Centralizado de Dados do Software
# ============================================================================

import json
from typing import Dict, List, Optional, Union, Tuple, Any

class Superestrutura:
    """Representa a configuração da superestrutura da ponte/viaduto."""
    def __init__(self, tipo: str, vaos: List[float], laje_transicao: Union[float, bool]):
        self.tipo = tipo
        self.vaos = vaos
        self.laje_transicao = laje_transicao

    def to_dict(self) -> Dict:
        return {"tipo": self.tipo, "vaos": self.vaos, "laje_transicao": self.laje_transicao}

    @classmethod
    def from_dict(cls, data: Dict) -> 'Superestrutura':
        return cls(tipo=data.get("tipo", ""), vaos=data.get("vaos", []), laje_transicao=data.get("laje_transicao", False))


class SecaoTransversal:
    """Representa a configuração da seção transversal da via."""

    # ── Mapa normalizado das classes padrão ──────────────────────────────────
    # Formato unificado: faixa, ac_ext, ac_int, pista_dupla, total  (valores em cm)
    # Usado por obter_config_via() — fonte única de verdade para as dimensões.
    _MAPA_CLASSES_PADRAO: Dict[str, Dict[str, Any]] = {
        "0":     {"faixa": 375, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True,  "total": 1190},
        "I - A": {"faixa": 360, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True,  "total": 1160},
        "I - B": {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False, "total": 1280},
        "II":    {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False, "total": 1280},
        "III":   {"faixa": 350, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False, "total": 1080},
        "IV":    {"faixa": 300, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False, "total":  980},
    }

    def __init__(self, classe: str, h_borda: float, h_centro: float,
                 inclincao: float, passeio: Union[float, bool],
                 dimensoes_personalizadas: Optional[Dict] = None):
        self.classe = classe
        self.h_borda = h_borda
        self.h_centro = h_centro
        self.inclinacao = inclincao
        self.passeio = passeio
        # Preenchido apenas quando classe == "Personalizado".
        # Formato: {faixa, ac_ext, ac_int, pista_dupla, total}  (valores em cm)
        self.dimensoes_personalizadas: Optional[Dict] = dimensoes_personalizadas

    # ------------------------------------------------------------------
    # Métodos de conveniência
    # ------------------------------------------------------------------

    def obter_config_via(self) -> Optional[Dict]:
        """
        Retorna a configuração normalizada da via com as chaves:
            faixa, ac_ext, ac_int, pista_dupla, total  (em cm)

        Para a classe 'Personalizado' devolve dimensoes_personalizadas.
        Retorna None se a configuração não estiver disponível.
        """
        if self.classe == "Personalizado":
            return self.dimensoes_personalizadas
        return self._MAPA_CLASSES_PADRAO.get(self.classe)

    def is_pista_dupla(self) -> bool:
        """Retorna True se a via é de pista dupla."""
        config = self.obter_config_via()
        return bool(config and config.get("pista_dupla", False))

    # ------------------------------------------------------------------
    # Serialização
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict:
        return {
            "classe": self.classe,
            "h_borda": self.h_borda,
            "h_centro": self.h_centro,
            "inclinacao": self.inclinacao,
            "passeio": self.passeio,
            "dimensoes_personalizadas": self.dimensoes_personalizadas,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SecaoTransversal':
        return cls(
            classe=data.get("classe", ""),
            h_borda=data.get("h_borda", 8.0),
            h_centro=data.get("h_centro", 10.0),
            inclincao=data.get("inclinacao", 2.0),
            passeio=data.get("passeio", False),
            dimensoes_personalizadas=data.get("dimensoes_personalizadas", None),
        )


class SecaoTransversalSuperestrutura:
    """Representa a geometria específica da superestrutura (longarinas, laje, etc)."""
    def __init__(self, n_longarinas: int, h_laje: float, d_extremidade: float,
                 largura_total: float, dados: dict, parametros_geometricos: dict,
                 largura_colaborante: Optional[float] = None):
        self.n_longarinas = n_longarinas
        self.h_laje = h_laje
        self.d_extremidade = d_extremidade
        self.largura_total = largura_total
        self.dados = dados
        self.parametros_geometricos = parametros_geometricos
        self.largura_colaborante = largura_colaborante

    def to_dict(self) -> Dict:
        return {
            "n_longarinas": self.n_longarinas,
            "h_laje": self.h_laje,
            "d_extremidade": self.d_extremidade,
            "largura_total": self.largura_total,
            "dados": self.dados,
            "parametros_geometricos": self.parametros_geometricos,
            "largura_colaborante": self.largura_colaborante
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SecaoTransversalSuperestrutura':
        return cls(
            n_longarinas=data.get("n_longarinas", 2),
            h_laje=data.get("h_laje", 25.0),
            d_extremidade=data.get("d_extremidade", 80.0),
            largura_total=data.get("largura_total", 0.0),
            dados=data.get("dados", {}),
            parametros_geometricos=data.get("parametros_geometricos", {}),
            largura_colaborante=data.get("largura_colaborante")
        )


class CoeficientesImpacto:
    """Armazena os dicionários de resultados da Calculadora de Coeficiente de Impacto."""
    def __init__(self, 
                 zonas_cia: Dict[Tuple[float, float], float], 
                 zonas_civ: Dict[Tuple[float, float], float], 
                 zonas_cnf: Dict[Tuple[float, float], float], 
                 zonas_impacto: Dict[Tuple[float, float], float]):
        self.zonas_cia = zonas_cia
        self.zonas_civ = zonas_civ
        self.zonas_cnf = zonas_cnf
        self.zonas_impacto = zonas_impacto

    def to_dict(self) -> Dict:
        def converter_chaves(dicionario):
            return {f"{k[0]};{k[1]}": v for k, v in dicionario.items()}

        return {
            "zonas_cia": converter_chaves(self.zonas_cia),
            "zonas_civ": converter_chaves(self.zonas_civ),
            "zonas_cnf": converter_chaves(self.zonas_cnf),
            "zonas_impacto": converter_chaves(self.zonas_impacto)
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'CoeficientesImpacto':
        def reverter_chaves(dicionario):
            if not dicionario: return {}
            resultado = {}
            for k, v in dicionario.items():
                partes = k.split(';')
                resultado[(float(partes[0]), float(partes[1]))] = v
            return resultado

        return cls(
            zonas_cia=reverter_chaves(data.get("zonas_cia", {})),
            zonas_civ=reverter_chaves(data.get("zonas_civ", {})),
            zonas_cnf=reverter_chaves(data.get("zonas_cnf", {})),
            zonas_impacto=reverter_chaves(data.get("zonas_impacto", {}))
        )


class Esforcos:
    """Armazena as tabelas de esforços e reações de uma análise."""
    def __init__(self, nome: str, cortante: List[List], momento: List[List], reacoes: List[List],
                 valores_limites: Optional[Dict[str, float]] = None):
        self.nome = nome
        self.cortante = cortante
        self.momento = momento
        self.reacoes = reacoes
        self.valores_limites = valores_limites if valores_limites is not None else {}

    def to_dict(self) -> Dict:
        return {
            "nome": self.nome,
            "cortante": self.cortante,
            "momento": self.momento,
            "reacoes": self.reacoes,
            "valores_limites": self.valores_limites
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Esforcos':
        return cls(
            nome=data.get("nome", ""),
            cortante=data.get("cortante", []),
            momento=data.get("momento", []),
            reacoes=data.get("reacoes", []),
            valores_limites=data.get("valores_limites", {})
        )


class TremTipoLongarina:
    """Representa os resultados do trem-tipo para as longarinas."""
    def __init__(self, caso_critico: Dict[str, float], resumo_resultados: Dict[str, Dict[str, float]]):
        self.caso_critico = caso_critico
        self.resumo_resultados = resumo_resultados

    def to_dict(self) -> Dict:
        return {
            "caso_critico": self.caso_critico,
            "resumo_resultados": self.resumo_resultados
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'TremTipoLongarina':
        return cls(
            caso_critico=data.get("caso_critico", {}),
            resumo_resultados=data.get("resumo_resultados", {})
        )


class EsforcosCalculo:
    """Armazena os resultados finais das combinações de esforços (ELU e ELS)."""
    def __init__(self, resultados: Dict[str, Dict]):
        self.resultados = resultados

    def to_dict(self) -> Dict:
        return {"resultados": self.resultados}

    @classmethod
    def from_dict(cls, data: Dict) -> 'EsforcosCalculo':
        return cls(resultados=data.get("resultados", {}))


class DataManager:
    """Gerencia todos os dados do software de forma centralizada."""
    def __init__(self):
        self.superestrutura: Optional[Superestrutura] = None
        self.secao_transversal: Optional[SecaoTransversal] = None
        self.secao_superestrutura: Optional[SecaoTransversalSuperestrutura] = None
        self.coeficientes_impacto: Optional[CoeficientesImpacto] = None
        self.trem_tipo_longarina: Optional[TremTipoLongarina] = None
        self.esforcos: Dict[str, Esforcos] = {}
        self.esforcos_calculo: Optional[EsforcosCalculo] = None

    def definir_superestrutura(self, tipo: str, vaos: List[float], laje_transicao: Union[float, bool]) -> Superestrutura:
        self.superestrutura = Superestrutura(tipo, vaos, laje_transicao)
        return self.superestrutura

    def get_superestrutura(self) -> Optional[Superestrutura]:
        return self.superestrutura

    def definir_secao_transversal(self, classe, h_borda, h_centro, incl, passeio,
                                   dimensoes_personalizadas=None) -> SecaoTransversal:
        """
        Cria e armazena a SecaoTransversal.
        Para classe == 'Personalizado', forneça dimensoes_personalizadas com as
        chaves: faixa, ac_ext, ac_int, pista_dupla, total  (valores em cm).
        """
        self.secao_transversal = SecaoTransversal(
            classe, h_borda, h_centro, incl, passeio, dimensoes_personalizadas
        )
        return self.secao_transversal

    def get_secao_transversal(self) -> Optional[SecaoTransversal]:
        return self.secao_transversal

    def definir_secao_superestrutura(self, n_longarinas, h_laje, d_extremidade,
                                     largura_total, dados, parametros_geometricos,
                                     largura_colaborante: Optional[float] = None) -> SecaoTransversalSuperestrutura:
        self.secao_superestrutura = SecaoTransversalSuperestrutura(
            n_longarinas, h_laje, d_extremidade, largura_total,
            dados, parametros_geometricos, largura_colaborante
        )
        return self.secao_superestrutura

    def get_secao_superestrutura(self) -> Optional[SecaoTransversalSuperestrutura]:
        return self.secao_superestrutura

    def definir_coeficientes_impacto(self, zonas_cia, zonas_civ, zonas_cnf, zonas_impacto) -> CoeficientesImpacto:
        self.coeficientes_impacto = CoeficientesImpacto(zonas_cia, zonas_civ, zonas_cnf, zonas_impacto)
        return self.coeficientes_impacto

    def get_coeficientes_impacto(self) -> Optional[CoeficientesImpacto]:
        return self.coeficientes_impacto

    def definir_trem_tipo_longarina(self, caso_critico: Dict[str, float], resumo_resultados: Dict[str, Dict[str, float]]) -> TremTipoLongarina:
        self.trem_tipo_longarina = TremTipoLongarina(caso_critico, resumo_resultados)
        return self.trem_tipo_longarina

    def get_trem_tipo_longarina(self) -> Optional[TremTipoLongarina]:
        return self.trem_tipo_longarina

    def definir_esforco(self, nome: str, cortante: List[List], momento: List[List], reacoes: List[List],
                        valores_limites: Optional[Dict[str, float]] = None) -> Esforcos:
        novo_esforco = Esforcos(nome, cortante, momento, reacoes, valores_limites)
        self.esforcos[nome] = novo_esforco
        return novo_esforco

    def get_esforco(self, nome: str) -> Optional[Esforcos]:
        return self.esforcos.get(nome)

    def definir_esforcos_calculo(self, resultados: Dict[str, Dict]) -> EsforcosCalculo:
        self.esforcos_calculo = EsforcosCalculo(resultados)
        return self.esforcos_calculo

    def get_esforcos_calculo(self) -> Optional[EsforcosCalculo]:
        return self.esforcos_calculo

    def limpar_dados(self):
        self.superestrutura = None
        self.secao_transversal = None
        self.secao_superestrutura = None
        self.coeficientes_impacto = None
        self.trem_tipo_longarina = None
        self.esforcos.clear()
        self.esforcos_calculo = None

    def exportar_dados(self, arquivo: str):
        dados = {
            "meta": {"software": "BridgeCalc", "versao": "1.0"},
            "superestrutura": self.superestrutura.to_dict() if self.superestrutura else None,
            "secao_transversal": self.secao_transversal.to_dict() if self.secao_transversal else None,
            "secao_superestrutura": self.secao_superestrutura.to_dict() if self.secao_superestrutura else None,
            "coeficientes_impacto": self.coeficientes_impacto.to_dict() if self.coeficientes_impacto else None,
            "trem_tipo_longarina": self.trem_tipo_longarina.to_dict() if self.trem_tipo_longarina else None,
            "esforcos": {k: v.to_dict() for k, v in self.esforcos.items()},
            "esforcos_calculo": self.esforcos_calculo.to_dict() if self.esforcos_calculo else None
        }
        with open(arquivo, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)

    def importar_dados(self, arquivo: str):
        with open(arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        self.limpar_dados()
        if dados.get("superestrutura"):
            self.superestrutura = Superestrutura.from_dict(dados["superestrutura"])
        if dados.get("secao_transversal"):
            self.secao_transversal = SecaoTransversal.from_dict(dados["secao_transversal"])
        if dados.get("secao_superestrutura"):
            self.secao_superestrutura = SecaoTransversalSuperestrutura.from_dict(dados["secao_superestrutura"])
        if dados.get("coeficientes_impacto"):
            self.coeficientes_impacto = CoeficientesImpacto.from_dict(dados["coeficientes_impacto"])
        if dados.get("trem_tipo_longarina"):
            self.trem_tipo_longarina = TremTipoLongarina.from_dict(dados["trem_tipo_longarina"])
        if dados.get("esforcos"):
            self.esforcos = {k: Esforcos.from_dict(v) for k, v in dados["esforcos"].items()}
        if dados.get("esforcos_calculo"):
            self.esforcos_calculo = EsforcosCalculo.from_dict(dados["esforcos_calculo"])
