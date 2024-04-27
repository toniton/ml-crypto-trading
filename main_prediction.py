from src.configuration.assets_config import AssetsConfig
from prediction.prediction_engine import PredictionEngine


def main():
    assets_config = AssetsConfig()
    assets = assets_config.assets

    prediction_engine = PredictionEngine(assets)
    prediction_engine.train_assets_model()


if __name__ == "__main__":
    main()
