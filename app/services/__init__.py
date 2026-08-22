"""Service package bootstrap for cross-cutting current provider contracts."""

from app.services.feed_publication_contract import install_feed_publication_contract
from app.services.kling_current_contract import install_current_kling_contracts
from app.services.trending_model_catalog import install_trending_model_catalog

install_current_kling_contracts()
install_trending_model_catalog()
install_feed_publication_contract()
