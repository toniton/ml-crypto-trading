from pandas import DataFrame, Series
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report
from sklearn.model_selection import RandomizedSearchCV, train_test_split

from joblib import parallel_backend


class RandomForestClassifierHelper:

    def __init__(self):
        self.n_estimators = range(50, 500, 15)
        self.min_samples_split = range(10, 150, 5)
        self.max_depth = range(1, 20)
        self.random_state = 5
        self.no_of_iterations = 50

    @staticmethod
    def _print_report(y_test, y_pred, best_params):
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred)
        recall = recall_score(y_test, y_pred)

        # Print the best hyperparameters
        print('Best hyperparameters:', best_params)

        print("Accuracy:", accuracy)
        print("Precision:", precision)
        print("Recall:", recall)
        print("Classification report:", classification_report(y_test, y_pred))
        print("Predictions:", y_pred)

    def train_model(self, data: DataFrame, target: Series) -> RandomForestClassifier:
        X_train, X_test, y_train, y_test = train_test_split(data, target, test_size=0.33)

        random_forest_classifier = RandomForestClassifier(
            random_state=self.random_state
        )
        param_dist = {
            'n_estimators': self.n_estimators,
            'min_samples_split': self.min_samples_split,
            'max_depth': self.max_depth
        }
        rand_search = RandomizedSearchCV(
            estimator=random_forest_classifier,
            param_distributions=param_dist,
            n_iter=self.no_of_iterations,
            cv=5
        )

        with parallel_backend('threading', n_jobs=12):
            rand_search.fit(X_train, y_train)

        best_rf = rand_search.best_estimator_
        best_params = rand_search.best_params_

        y_pred = best_rf.predict(X_test)
        self._print_report(y_test, y_pred, best_params)

        return best_rf
