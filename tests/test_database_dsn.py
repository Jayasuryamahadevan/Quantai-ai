from sqlalchemy.engine.url import make_url
from app.config import Settings


def test_special_characters_in_mysql_password(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = Settings(
        mysql_readonly_password="a@b:c/d?e#f%g",
        mysql_readonly_user="readonly_user",
        mysql_data_schema="quantai_data",
    )
    url = make_url(cfg.readonly_dsn)
    assert url.password == "a@b:c/d?e#f%g"
    assert url.username == "readonly_user"
    assert url.database == "quantai_data"
