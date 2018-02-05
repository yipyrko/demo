import json

from django.http import QueryDict
from rest_framework.generics import GenericAPIView

from rest_framework.permissions import IsAuthenticated

from admin_panels.serializers import MealCategoryWithMealsSerializer
from gloodny.models import MealCategory, Meal, SubMeal, MealOptionCategory, MealOption
from gloodny.serializers import MealSerializer, SubMealSerializer
from gloodny.utils import get_restaurant


class RestaurantMixin(object):

    @property
    def restaurant(self):
        """
        :return: restaurant by request
        """
        return get_restaurant(self.request)

    def update_serializer(self, qdict, instance=None):
        """
        :param qdict: requset data
        :return: serializer
        Update restaurant_id into serializer
        """
        serializer = self.get_serializer(instance=instance, data=qdict)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data['restaurant_id'] = self.restaurant.id
        return serializer


class BaseMealCategoryMixin(RestaurantMixin, GenericAPIView):
    """
        BaseMealCategoryMixin
    """
    permission_classes = (IsAuthenticated,)
    model = MealCategory
    serializer_class = MealCategoryWithMealsSerializer


class MealCategoryQuerySetMixin(BaseMealCategoryMixin):

    def get_queryset(self):
        """
            return: queryset of categories by restaurant
        """
        return MealCategory.get_categories_by_restaurant_id(self.restaurant.id)


class MealMixin(RestaurantMixin):
    serializer_class = MealSerializer

    @staticmethod
    def set_default_order(data):
        """
        :param data: request data
        Update default  meal order
        """
        data['order'] = 0

    def parse_request_data(self):
        """
        :return: query dict for correctly work serializer
        From front end we get two types params
        first format we can get from request.data as usual this data without photo,
        and second format 'Upload.upload' sending data in request.POST and we are getting file here.
        """
        # TODO: make changes to use only single format (changes required on FE and BE sides).
        if self.request.POST.get('data'):
            data = json.loads(self.request.POST['data'])
            qdict = QueryDict('', mutable=True)
            qdict.update(data)
        else:
            qdict = self.request.data

        # Set default order for new meal
        if not qdict.get('id'):
            MealMixin.set_default_order(qdict)
        return qdict

    def update_orderings_in_category_brefore_create(self, data):
        """
        :param data: request data
        Update all orders in selected category
        """
        if data.get('selectedCateg') and data['selectedCateg'].get('id'):
            Meal.update_orderings_in_category(data['selectedCateg']['id'])

    def set_meal_data(self, instance, data):
        """
        :param instance: meal object
        :param data: request data
        """
        self.update_meal_picture(instance)
        self.update_meal_submeals(instance, data)
        self.update_meal_options(instance, data)

    def update_meal_picture(self, instance):
        """
        :param instance: meal object
        """
        # If file in request.FILES call meal update_picture
        if self.request.FILES.get('file'):
            instance.update_picture(self.request.FILES['file'])

    def update_meal_submeals(self, instance, data):
        """
        :param instance: meal object
        :param data: request data
        """
        # If submeals in data call meal update_submeals
        instance.clear_submeals()
        if data.get('submeals'):
            instance.add_submeals([submeal['id'] for submeal in data['submeals']])

    def create_meal_options(self, options, category):
        """
        :param options: options additional
        :param category: options category
        """
        # Create list of objects
        # Use bulk create create new options
        for meal_order, meal_option in enumerate(options):
            MealOption.create_meal_option(self.get_data_for_meal_option(category, meal_option, meal_order))

    def get_data_for_meal_option(self, category, meal_option, meal_order):
        """
        :param category: options category
        :param meal_option: option dict
        :param meal_order: order
        :return: dict for create option
        """
        return {
            "option_category_id": category.id,
            "price": meal_option['price'],
            "name": meal_option['name'],
            "order": meal_order
            }

    def get_data_for_meal_category_option(self, name, order):
        """
        :param name: category name
        :param order: order
        :return: dict for create category
        """
        return {
            "name": name,
            "restaurant": self.restaurant,
            "order": order
            }

    def update_meal_options(self, instance, data):
        """
        :param instance: meal object
        :param data: request data
        :return:
        """
        # If option_categories in data create option category, and options
        # call meal update_option_categories
        if data.get('option_categories'):
            option_categories = self.create_option_category(data)
            instance.update_option_categories(option_categories)
        else:
            instance.option_categories.clear()

    def create_option_category(self, data):
        """
        :param data: request data
        :return: new option_categories
        """
        option_categories = []
        for order, option_category in enumerate(data['option_categories']):
            # Get data for create category and create it
            category_data = self.get_data_for_meal_category_option(option_category['name'], order)
            category = MealOptionCategory.create_option_category(category_data)
            # Call method for create otions
            self.create_meal_options(option_category['options'], category)
            option_categories.append(category.id)
        return option_categories

    def update_meal_category(self, instance, data, old_instance_meal_categories, old_instance_order):
        """
        :param instance: meal object
        :param data: request data
        :param old_instance_meal_categories:  old meal category
        :param old_instance_order: old meal order
        :return:
        """
        # Update category for existing meal if category was changed
        if data.get('selectedCateg') and data['selectedCateg'] not in instance.meal_categories_ids:

            # Update meals ordering into old category
            instance.update_old_ordering_in_category(old_instance_meal_categories, old_instance_order)

            # Update meal category
            instance.update_category(data['selectedCateg']['id'])

            # Update meals ordering into new category
            Meal.update_orderings_in_category(data['selectedCateg']['id'])

            # Set meal order 0 if meal was moved from different category
            instance.order = 0

    def set_meal_category(self, instance, data):
        """
        :param instance: meal object
        :param data: request data
        """
        # Set category for new meal
        if data.get('selectedCateg') and data['selectedCateg'].get('id'):
            instance.update_category(data['selectedCateg']['id'])
