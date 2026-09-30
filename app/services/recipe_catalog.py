from app.services.recipe_data import RECIPES

class RecipeCatalog:
    def __init__(self):
        self.recipes = RECIPES
        
    def get_all(self):
        return self.recipes
        
    def get_by_id(self, recipe_id: str):
        for r in self.recipes:
            if r['id'] == recipe_id:
                return r
        return None

catalog = RecipeCatalog()
