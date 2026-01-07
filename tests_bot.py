import unittest
from ai_integration_code import generate_portfolio

class TestPortfolioBot(unittest.TestCase):
    
    def test_weights_sum(self):

        result = generate_portfolio("сумма 100000 на 1 год")
        weights = extract_weights(result)  # вспомогательная функция
        self.assertAlmostEqual(sum(weights), 1.0, delta=0.01)
    
    def test_risk_calculation(self):
        risk = extract_risk(result)
        self.assertLessEqual(risk, 0.30)
if __name__ == '__main__':
    unittest.main()
