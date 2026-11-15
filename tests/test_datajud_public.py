"""Padrão público oficial sem sobrescrever a configuração do usuário."""
from atlas_worker.config import Settings
from atlas_worker.config_store import ConfigStore, defaults
from atlas_worker.datajud_public import DATAJUD_PUBLIC_KEY


def test_padrao_publico_ausente_vazio_e_personalizado(tmp_path):
    base={'RADAR_API_URL':'https://exemplo.invalid/api/v1','WORKER_NAME':'pc-teste','WORKER_TOKEN':'ficticio'}
    for extra in ({},{'DATAJUD_API_KEY':''},{'DATAJUD_API_KEY':'  '}):
        assert Settings(_env_file=None,**base,**extra).datajud_api_key.get_secret_value()==DATAJUD_PUBLIC_KEY
    store=ConfigStore(tmp_path/'.env')
    cfg=store.save({**base,'DATAJUD_API_KEY':'chave-personalizada-ficticia','OPCAO_EXTRA':'preservada'})
    assert cfg.datajud_api_key.get_secret_value()=='chave-personalizada-ficticia'
    assert store.load()['OPCAO_EXTRA']=='preservada'
    assert defaults()['DATAJUD_API_KEY']==DATAJUD_PUBLIC_KEY
