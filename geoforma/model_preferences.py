"""Validated last-model preferences, separate from project-specific configuration."""
import json
import os
from .model_catalog import model_spec

LAST_MODEL_KEY='model/last_used'


def recommended_model():
    from .weights import default_checkpoint
    return {'backend':'sam2.1','variant':'small','device':'cuda','execution':'auto',
            'checkpoint':str(default_checkpoint('small','sam2.1'))}


def normalize_model(config):
    if not isinstance(config,dict):raise ValueError('Model preference must be an object.')
    backend=config.get('backend','sam');variant=config['variant'];model_spec(variant,backend)
    device=config.get('device','cuda')
    if device not in ('cuda','cpu'):raise ValueError('Unsupported model device preference.')
    if config.get('execution','auto') not in ('auto','native'):raise ValueError('Unsupported model runtime.')
    from .weights import default_checkpoint
    path=config.get('checkpoint','')
    if not isinstance(path,str):raise ValueError('Checkpoint preference must be a path string.')
    return {'backend':backend,'variant':variant,'device':device,'execution':'auto',
            'checkpoint':path.strip() or str(default_checkpoint(variant,backend))}


def application_settings():
    from PySide6.QtCore import QSettings
    # Optional explicit location is used by portable diagnostics and isolated tests.
    path=os.environ.get('GEOFORMA_SETTINGS_FILE')
    return QSettings(path,QSettings.Format.IniFormat) if path else QSettings('GeoForma','GeoForma')


def last_model(settings):
    try:return normalize_model(json.loads(settings.value(LAST_MODEL_KEY,'')))
    except (TypeError,ValueError,KeyError):return recommended_model()


def remember_model(settings,config):
    try:value=normalize_model(config)
    except (TypeError,ValueError,KeyError):return False
    encoded=json.dumps(value,ensure_ascii=False,sort_keys=True)
    if settings.value(LAST_MODEL_KEY,'')==encoded:return settings.status()==settings.Status.NoError
    settings.setValue(LAST_MODEL_KEY,encoded)
    settings.sync()
    return settings.status()==settings.Status.NoError
