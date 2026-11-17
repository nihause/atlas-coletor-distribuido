import json
import logging

from atlas_worker.logging_config import setup


def test_erros_jsonl_com_versao_e_sem_credenciais(tmp_path):
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    root.handlers = []
    try:
        setup('INFO', tmp_path, ['chave-teste-secreta'])
        logging.getLogger('atlas_worker.teste').info('mensagem informativa')
        try:
            raise ValueError('token=chave-teste-secreta')
        except ValueError:
            logging.getLogger('atlas_worker.teste').exception('tarefa 42 falhou: chave-teste-secreta')
        for handler in root.handlers: handler.flush()
        text = (tmp_path / 'logs' / 'erros.jsonl').read_text()
        records = [json.loads(line) for line in text.splitlines()]
        assert len(records) == 1 and records[0]['task_id'] == 42
        assert records[0]['version'] and records[0]['level'] == 'ERROR'
        assert 'chave-teste-secreta' not in text and 'ValueError' in records[0]['detail']
    finally:
        for handler in root.handlers: handler.close()
        root.handlers, root.level = handlers, level
