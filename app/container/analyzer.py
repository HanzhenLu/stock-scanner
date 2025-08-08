from app.services.analyzer import WebStockAnalyzer
analyzer:WebStockAnalyzer = None

def set_analyzer(instance):
    global analyzer
    analyzer = instance

def get_analyzer():
    return analyzer
