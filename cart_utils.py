from django.contrib.sites.shortcuts import get_current_site
from gloodny.utils import *
from .models import Meal, SubMeal, MealOption, CartLine, Restaurant


class Cart(object):
    """
    Wraps cart implementation. Provides clean interface for adding/removing meals

    Convert all CartLine objects into a dictionary
    containing two dicts: meals and submeals
    Sample structure is

    cart = {
        meals: {
            meal_id: [
                {options: [option1_id, option2_id], quantity: quantity},
                {options: [option1_id], quantity: quantity},
            ]
        },
        submeals: {
            submeal_id: quantity
        },
        restaurant_id: id
    }
    """
    def __init__(self, cart=None):
        if cart is None:
            self.meals = {}
            self.submeals = {}
        else:
            self.meals = cart.get('meals', {})
            self.submeals = cart.get('submeals', {})

    def get_total_price(self):
        cart_lines = self.get_cartlines(None)
        return self.total_price(cart_lines)

    def get_total_quantity(self):
        meals = sum(self.meals_with_quantities().values())
        submeals = sum(self.submeals.values())
        return meals + submeals

    def add_meal(self, meal_id, options_ids, number):
        options_ids = self.set_valid_options(options_ids)
        meal_id = str(meal_id)
        meal_index = self.get_meal_index(meal_id, options_ids)
        meal_dict = {'quantity': number, 'options': options_ids}

        if self.meals.get(meal_id) and meal_index is not None:
            self.meals[meal_id][meal_index]['quantity'] += number
        elif self.meals.get(meal_id):
            self.meals[meal_id].append(meal_dict)
        else:
            self.meals.update({meal_id: [meal_dict]})

    def remove_meal(self, meal_id, options_ids):
        meal_id = str(meal_id)
        meal_index = self.get_meal_index(meal_id, options_ids)
        if self.meals.get(meal_id) and meal_index is not None:
            del self.meals[meal_id][meal_index]

    def add_submeal(self, submeal_id, number):
        try:
            self.submeals[str(submeal_id)] += number
        except KeyError:
            self.submeals[str(submeal_id)] = number

    def remove_submeal(self, submeal_id):
        del self.submeals[str(submeal_id)]

    def get_meals(self):
        return Meal.objects.filter(pk__in=self.meals.keys())

    def get_submeals(self):
        return SubMeal.objects.filter(pk__in=self.submeals.keys())

    def meals_with_quantities(self):
        meals = {}
        for meal in self.get_meals():
            quantity = sum(quantity['quantity'] for quantity in self.meals[str(meal.id)])
            meals[meal] = quantity
        return meals

    @property
    def restaurant(self):
        """
        FIXME: doesn't support ordering from multiple restaurants
        """
        return Restaurant.get_by_id(self.restaurant_id)

    def submeal_quantity(self, submeal_id):
        return self.submeals[str(submeal_id)]

    def meal_quantity(self, meal_id, options_ids):
        for meal in self.meals.get(meal_id, []):
            if set(meal['options']) == set(options_ids):
                return meal['quantity']
        # If meal_id not exist in current session cart return None
        return None

    def line_quantity(self, line):
        if isinstance(line.product, Meal):
            options_ids = self.set_valid_options(line.options_ids)
            quantity = self.meal_quantity(line.meal_key, options_ids)
        else:
            quantity = self.submeal_quantity(line.meal_key)

        return quantity

    def meal_options(self, meal_id):
        return self.meals[str(meal_id)]

    def total_price(self, cartlines):
        total_price = 0
        for line in cartlines:
            options_price = sum(option.price for option in line.options)
            total_price += (line.product.price + options_price) * line.quantity

        return total_price

    def to_dict(self):
        return {'meals': self.meals, 'submeals': self.submeals}

    def get_cartlines(self, user):
        """
        Initialize cart lines objects from cart
        """
        cart_lines = []

        for meal in self.get_meals():
            for options in self.meals[str(meal.id)]:
                cart_line = CartLine(
                    quantity=options['quantity'],
                    product=meal,
                    user=user if user and user.is_authenticated() else None)
                # save meal options to the attribute, because it can't be added to m2m field
                # before cartline is actually saved into db
                if options:
                    cart_line.options = MealOption.get_options_by_ids(options['options'])
                else:
                    cart_line.options = []
                cart_lines.append(cart_line)

        for submeal in self.get_submeals():
            cart_line = CartLine(
                quantity=self.submeals[str(submeal.id)],
                product=submeal,
                user=user if user and user.is_authenticated() else None
            )
            cart_line.options = []
            cart_lines.append(cart_line)

        return cart_lines

    @classmethod
    def create_from_cartlines(cls, cartlines):
        cart = cls()
        for line in cartlines:
            if isinstance(line.product, Meal):
                cart.add_meal(line.product.id, line.options_ids, line.quantity)
            elif isinstance(line.product, SubMeal):
                cart.add_submeal(line.product.id, line.quantity)
        return cart

    def get_meal_index(self, meal_id, options):
        for index, meal in enumerate(self.meals.get(meal_id, [])):
            if set(meal['options']) == set(options):
                return index
        return None

    def set_valid_options(self, options):
        return [int(option) for option in options]

    def fetch_cart(self, request):
        restaurant_site = get_current_site(request)
        restaurant = Restaurant.get_by_site(restaurant_site)

        delivery_time = 0
        gloodny_address = request.session.get('gloodny_address')
        if gloodny_address and gloodny_address.get('point') and gloodny_address['point'].get('lat'):
            pnt = get_point_object(gloodny_address['point']['lat'], gloodny_address['point']['lng'])
            meals = self.meals_with_quantities()
            if meals:
                pickup_times = get_pickup_times(meals)
                delivery_time = get_delivery_time(pickup_times, pnt)

        cart_items = {
            'meals': Meal.get_meals_list(self.get_meals(), self),
            'submeals': SubMeal.get_submeals_list_by_cart(self)
        }

        response = {
            'items': cart_items,
            'user_email': request.user.email if request.user.is_authenticated() else '',
            'delivery_time': int(delivery_time) if delivery_time else 0,
            'open_hours': restaurant.format_open_hours if not restaurant.closed() else None,
            'delivery_start_hours': timefield_delta_format(restaurant.open_hours, 45) if restaurant.closed() else None,
            'close_hours': timefield_delta_format(restaurant.close_hours, -60) if restaurant.closed() else None,
        }
        return response

    def remove_meals_list(self, meals_list):
        for meal in meals_list:
            del self.meals[str(meal)]

    def remove_submeals_list(self, submeals_list):
        for submeal in submeals_list:
            del self.submeals[str(submeal)]
