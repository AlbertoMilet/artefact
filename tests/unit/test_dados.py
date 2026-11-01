"""Carga e normalização dos dados (CA-10, RN-13, A10, A11)."""

import shutil
from decimal import Decimal

import pytest

from emporio.data import DadosIndisponiveis, carregar
from tests.conftest import RAIZ


def test_carga_completa_dos_dados_reais(catalogo):
    assert len(catalogo.produtos) == 65
    assert len(catalogo.pedidos) == 20
    assert len(catalogo.clientes) == 50
    assert len(catalogo.promocoes) == 25
    assert catalogo.descartes == []
    assert catalogo.produtos[95].price_brl == Decimal("2199")


def _copia_dados(tmp_path):
    destino = tmp_path / "data"
    shutil.copytree(RAIZ / "data", destino)
    return destino


def test_ca10_arquivo_obrigatorio_ausente_impede_inicializacao(tmp_path):
    data = _copia_dados(tmp_path)
    (data / "desafio_tecnico_ai_eng - products.csv").unlink()
    with pytest.raises(DadosIndisponiveis, match="products"):
        carregar(data)


def test_ca10_linha_com_specs_invalido_e_descartada_e_o_resto_continua(tmp_path):
    data = _copia_dados(tmp_path)
    arq = data / "desafio_tecnico_ai_eng - products.csv"
    linhas = arq.read_text(encoding="utf-8").splitlines()
    linhas.append('999,100,Produto Quebrado,5,teste,1,active,"{nao e json",2024-01-01')
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    c = carregar(data)
    assert 999 not in c.produtos
    assert len(c.produtos) == 65
    assert any("products.csv" in d for d in c.descartes)


def test_ca10_referencia_quebrada_e_descartada(tmp_path):
    data = _copia_dados(tmp_path)
    arq = data / "desafio_tecnico_ai_eng - promotions.csv"
    arq.write_text(arq.read_text(encoding="utf-8").rstrip("\n") + "\n99,4242,10,Fantasma,1\n", encoding="utf-8")
    c = carregar(data)
    assert all(p.product_id != 4242 for p in c.promocoes)
    assert any("promoção 99" in d for d in c.descartes)


def test_marca_vem_do_nome(catalogo):
    assert catalogo.produtos[95].marca == "Takamine"
    assert catalogo.produtos[135].marca == "Music Man"      # descrição diz Fender (A10)
    assert all(p.marca for p in catalogo.produtos.values())


def test_descricao_nao_confiavel_nos_produtos_contraditorios(catalogo):
    nao_confiaveis = {pid for pid, p in catalogo.produtos.items() if not p.descricao_confiavel}
    assert nao_confiaveis == {135, 137, 139, 140, 142, 144}


def test_specs_strings_normalizado_por_categoria(catalogo):
    assert catalogo.produtos[95].specs_normalizadas["material_cordas"] == "aço"
    assert catalogo.produtos[81].specs_normalizadas["material_cordas"] == "nylon"
    assert catalogo.produtos[135].specs_normalizadas["num_cordas"] == 4


def test_id_duplicado_mantem_o_primeiro_e_registra(tmp_path):
    data = _copia_dados(tmp_path)
    arq = data / "desafio_tecnico_ai_eng - products.csv"
    linhas = arq.read_text(encoding="utf-8").splitlines()
    linhas.append('95,1,Takamine Falso,5,teste,1,active,{},2024-01-01')
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    c = carregar(data)
    assert c.produtos[95].name == "Takamine GD20 Dreadnought Natural"
    assert any("produto 95 duplicado" in d for d in c.descartes)
