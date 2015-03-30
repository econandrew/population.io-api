#from algorithms import *
#from dateutil.relativedelta import *
import datetime
import time
import os.path
import cPickle as pickle
import numpy as np
import csv
from collections import defaultdict

from scipy.interpolate import RectBivariateSpline


###################################################################################################
# Base Class
###################################################################################################

class PopulationModel(object):
    '''
    An abstract base class for a population model, which is fundamentally defined as
        population = f(region, sex, age, [enumeration] date)
    
    Dates and ages in this framework are always integers, and supported date and age ranges
    are assumed to be contiguous. The semantics of these types is left up to the individual
    implementing class. Although all the subclasses at present, treat them either as years
    or as days, it wouldn't be difficult to represent (e.g.) 5-year groupings this way.
    '''
    
    def get_regions(self):
        '''Return a list of regions supported by the model.'''
        raise NotImplementedError
        
    def regions(self):
        '''Return an iterator over regions'''
        return iter(self.get_regions())
        
    def get_age_range(self):
        '''Return a tuple containing inclusive age boundaries (min_age, max_age)'''
        raise NotImplementedError

    def ages(self):
        '''Return an iterator over ages'''
        min_age, max_age = self.get_age_range()
        return range(min_age, max_age+1)
        
    def get_sexes(self):
        '''Return a list of sexes supported by the model'''
        raise NotImplementedError

    def sexes(self):
        '''Return an iterator over sexes'''
        return iter(self.get_sexes())
        
    def get_date_range(self):
        '''Return a tuple containing inclusive date boundaries (min_date, max_date)'''        
        raise NotImplementedError
        
    def dates(self):
        '''Return an iterator over ages'''
        min_date, max_date = self.get_date_range()
        return range(min_date, max_date+1)        
                
    def check_age(self, age, default_age = None, truncate = False):
        '''
        A helper function that checks that an age is in range, either truncates it or
        raises a ValueError if not, and potentially sets it to a default (an integer
        if given or special strings "max" and "min" are recognised).
        
        It may not always be appropriate to continue raising this exception - it may
        make sense to return 0 for an age outside model range (e.g. > 100).
        '''
        min_age, max_age = self.get_age_range()
        if age is None:
            if default_age == "min":
                age = min_age
            elif default_age == "max":
                age = max_age
            else:
                age = default_age
            
        if age < min_age:
            if truncate:
                age = min_age
            else:
                raise ValueError("Age outside valid range", age, (min_age, max_age))

        if age > max_age:
            if truncate:
                age = max_age
            else:
                raise ValueError("Age outside valid range", age, (min_age, max_age))

        return age
        
    def check_date(self, date, default_date = None):
        '''
        A helper function that checks that an date is in range,
        raises a ValueError if not, and potentially sets it to a default (an integer
        if given or special strings "max" and "min" are recognised).
        '''
        min_date, max_date = self.get_date_range()
        if date is None:
            if default_date == "min":
                date = min_date
            elif default_date == "max":
                date = max_date
            else:
                date = default_date
        
        if not(min_date <= date <= max_date):
            raise ValueError("Date outside valid range", date, (min_date, max_date))

        return date
    
    def pop_age(self, date, region, sex, age):
        '''
        The fundamental building block: return the population for the given parameters.
        Must be overridden in concrete implementations.
        '''
        raise NotImplementedError
        
    def pop_dob(self, date, region, sex, dob):
        '''
        Return the population for the given parameters (based on dob not age).
        May be overridden for efficiency.
        '''
        age = date - dob
        return self.pop_age(date, region, sex, age)
        
    def pop_sum_age(self, date, region, sex, age_from = None, age_to = None):
        '''
        Return the population for the given parameters from age_from to age_to (inclusive).
        This naive implementation may be overriden for efficiency.
        '''
        age_from = self.check_age(age_from, "min", truncate=True)
        age_to = self.check_age(age_to, "max", truncate=True)
           
        multiage_pop = 0
        for age in range(age_from, age_to+1):
            multiage_pop += self.pop_age(date, region, sex, age)
            
        return multiage_pop
        
    def pop_sum_dob(self, date, region, sex, dob_from = None, dob_to = None):
        '''
        Return the population for the given parameters from dob_from to dob_to (inclusive).
        This naive implementation may be overriden for efficiency.
        '''
        age_range = self.get_age_range()
        if dob_from is None: # zero may be a valid value
            dob_from = date - age_range[1]
        if dob_to is None:
            dob_to = date - age_range[0]
            
        multidob_pop = 0
        for dob in range(dob_from, dob_to+1):
            multidob_pop += self.pop_dob(date, region, sex, dob)
        
        return multidob_pop

    def pop_sum_dob_inverse_date(self, pop, region, sex, dob, date_from = None, date_to = None):
        '''
        Return the date on which a person born on dob would become the pop'th youngest
        person (rank) then alive. This is a simple binary search which is relatively quick, but
        assumes this rank only occurs once, which may not be true for certain populations.
        
        If you specify date_from or date_to it will constrain the search to that period.
        '''
        date_lower = date_from or dob
        date_upper = date_to or self.get_date_range()[1]
        pop_lower = self.pop_sum_dob(date_lower, region, sex, dob, date_lower)
        pop_upper = self.pop_sum_dob(date_upper, region, sex, dob, date_upper)
        
        def midpoint(lower, upper):
            return lower + (upper - lower) / 2
        
        while date_upper - date_lower > 1:   
            date_midpoint = midpoint(date_lower, date_upper)
            pop_midpoint = self.pop_sum_dob(date_midpoint, region, sex, dob, date_midpoint)

            if pop_midpoint < pop:
                date_lower, pop_lower = date_midpoint, pop_midpoint
            else:
                date_upper, pop_upper = date_midpoint, pop_midpoint
                
        if pop_lower <= pop <= pop_upper or (pop == 0): # pop == 0: FIXME b/c otherwise 0 population outside range
            return date_lower
        else:
            raise ValueError("The chosen population was not found (maybe outside range?)", pop, pop_lower)
        

###################################################################################################
# Single Year Model
###################################################################################################

class NpSingleYearPopulationModel(PopulationModel):
    '''
    A numpy-based implementation of a single-year (of age and of enumeration date) population model
    loaded from CSV.
    '''
    def _age_index(self,age):
        '''Convert an age into an index into the numpy array'''
        return int(age)-self.age_range[0]
        
    def _date_index(self,date):
        '''Convert a date into an index into the numpy array'''
        return int(date)-self.date_range[0]
        
    def __init__(self, filename, check_or_create_pickle = False):
        self.age_range = (0, 100)
        self.date_range = (1950,2100)
        self.sexes = ('M','F', 'All')
        self.arrays = None
        if check_or_create_pickle and os.path.isfile(filename + ".pickle"):
            with open(filename + ".pickle", "rb") as file:
                self.arrays = pickle.load(file)
        else:
            self._load_pop_csv(filename)
            if check_or_create_pickle:
                with open(filename + ".pickle", "wb") as file:
                    pickle.dump(self.arrays, file)
        

        self.arrays = dict(self.arrays)

    def _load_pop_csv(self, filename):
        '''Load the CSV file into a dictionary-of-dictionaries of arrays for quick access.'''
        self.arrays = defaultdict(lambda: defaultdict(lambda: np.empty((self.age_range[1]-self.age_range[0]+1, self.date_range[1]-self.date_range[0]+1))))

        with open(filename, 'r') as file:
            reader = csv.DictReader(file)
            # ?, LocID, Location (Country), VarID, Variant, Time, Age, pop male, pop female, pop total

            for row in reader:
                loc_dict = self.arrays[row['Location']]
                loc_dict['M'][self._age_index(row['Age']), self._date_index(row['Time'])] = round(float(row['PopMale'])*1000)
                loc_dict['F'][self._age_index(row['Age']),self._date_index(row['Time'])] = round(float(row['PopFemale'])*1000)
                loc_dict['All'][self._age_index(row['Age']),self._date_index(row['Time'])] = round(float(row['PopTotal'])*1000)

        for loc in self.arrays:
            self.arrays[loc] = dict(self.arrays[loc])

        self.arrays = dict(self.arrays)
        
    def get_regions(self):
        return self.arrays.keys()
        
    def get_age_range(self):
        return self.age_range
        
    def get_sexes(self):
        return self.sexes
        
    def get_date_range(self):
        return self.date_range
        
    def pop_age(self, date, region, sex, age):
        date = self.check_date(date)
        try:
            age = self.check_age(age)
        except ValueError:
            return 0 # Return 0 for outside-range ages, since this model is intended to be complete
        
        return int(self.arrays[region][sex][self._age_index(age),self._date_index(date)])
        

###################################################################################################
# Single Day Model
###################################################################################################

DAYS_PER_YEAR = 365.25
EPOCH = datetime.date(1970, 1, 1)
ONE_DAY = datetime.timedelta(days=1)

def to_epoch_days(date):
    return (date - EPOCH).days
    
def from_epoch_days(days):
    delta = datetime.timedelta(days = days)
    return EPOCH + delta

def days_to_decimal_year(days, start_month=1, start_day=1):
    '''
    Returns the decimal year represented by a number of epoch days. A decimal year is, for example
    2005.25, which represents a day at the end of the first quarter of 2005. The decimal year is 
    returned as a pair (2005, 0.25). The month and day in which a year beings can optionally be
    specified otherwise defaults to 1 January.
    '''
    date = from_epoch_days(days)
    year = date.year

    # First try the same calendar year as the start year...
    year_start = datetime.date(year, start_month, start_day)
    year_start_days = to_epoch_days(year_start)
    if (year_start_days > days):
        # ...but for years that don't align with calendar we may have to look back one
        year = year - 1
        year_start = datetime.date(year, start_month, start_day)
        year_start_days = to_epoch_days(year_start)

    year_end = datetime.date(year+1, start_month, start_day)
    year_length = (year_end - year_start).days

    frac = (days - year_start_days) / float(year_length) # force float division
    return year, frac

def decimal_year_to_days(year, frac, start_month=1, start_day=1):
    '''See days_to_decimal_year()'''
    year_start = datetime.date(year, start_month, start_day)
    year_start_days = to_epoch_days(year_start)
    year_end = datetime.date(year+1, start_month, start_day)
    year_length = (year_end - year_start).days

    days = year_start_days + frac * year_length
    return days

class DailyPopulationModel(PopulationModel):
    '''
    Another abstract class for building daily population models that build upon and interpolate
    some single-year base population model. Adds some more common helpers.
    '''    
    def __init__(self, base_model, enum_month = 7, enum_day = 1):
        self.base_model = base_model
        self.enum_month = enum_month
        self.enum_day = enum_day

    def get_regions(self):
        return self.base_model.get_regions()
        
    def get_age_range(self):
        min_years, max_years = self.base_model.get_age_range()
        return (int(min_years * DAYS_PER_YEAR), int((max_years + 1) * DAYS_PER_YEAR) - 1)
        
    def get_sexes(self):
        return self.base_model.get_sexes()
        
    def get_date_range(self):
        min_year, max_year = self.base_model.get_date_range()
        min_days = to_epoch_days(datetime.date(min_year, self.enum_month, self.enum_day))
        max_days = to_epoch_days(datetime.date(max_year, self.enum_month, self.enum_day))
        return (min_days, max_days)
    
    def get_enum_year_frac(self,date):
        '''
        Gets the year and fraction relative to 'enumeration years' which begin on the enumeration
        date each year. So 31 December 2005 would be (roughly) 2005.5 since it lies halfway between
        the 2005 enumeration and the 2006 enumeration.
        '''
        return days_to_decimal_year(date, self.enum_month, self.enum_day)
        
    def get_age_year_frac(self, age):
        '''
        Convert the age in days to a fractional year, e.g. 25.75 = 25 years and 9 months returns
        (25, 0.75).
        '''
        age_years_float = age / DAYS_PER_YEAR
        age_years = int(age_years_float)
        age_frac = age_years_float - age_years
        return age_years, age_frac

class BicubicSplineDailyPopulationModel(DailyPopulationModel): 
    '''
    An implementation of a daily population model that uses bicubic (ie. two dimensional) splines
    to interpolate both over age and over enumeration date.
    '''           
    def __init__(self, base_model, enum_month = 7, enum_day = 1):
        super(BicubicSplineDailyPopulationModel, self).__init__(base_model, enum_month, enum_day)
        self.models = defaultdict(lambda: dict())
    
    def get_model(self, region, sex):
        '''
        Get the interpolation model for a given region and sex. If not available, build the
        model. Call build_all_models() to force precomputation of all interpolations, which will
        save time when calls are made later.
        '''
        try:
            return self.models[region][sex]
        except KeyError:
            self.models[region][sex] = self.build_model(region, sex)
            return self.models[region][sex]
            
    def build_all_models(self):
        for region in self.get_regions():
            for sex in self.get_sexes():
                self.get_model(region, sex)
            
    def build_model(self, region, sex):
        '''
        Set up the interpolation model for a given region and sex. The majority of the work here is
        in setting up an array of grid points - the actual interpolation is handled by numpy.
        '''
        min_b_age, max_b_age = self.base_model.get_age_range()
        min_b_date, max_b_date = self.base_model.get_date_range()
        pop = np.empty((max_b_age - min_b_age + 1, max_b_date - min_b_date + 1))
        for age_idx in range(0, max_b_age - min_b_age + 1):
            for date_idx in range(0, max_b_date - min_b_date + 1):
                pop[age_idx, date_idx] = self.base_model.pop_age(min_b_date + date_idx, region, sex, min_b_age + age_idx)
                
        # Since we're disaggregating here, we need to take people born throughout a year and impute
        # the number born on a given day. We assume even distribution across all days of a typical
        # year.
        pop = pop / float(DAYS_PER_YEAR) # divide through the entire array by scalar

        # Now define where the grid points are. For ages, it's halfway through the age-year, since
        # e.g. people age 0 are on average actually 0.5 (assuming even distribution). For dates
        # it is on the enumeration day given in the constructor.
        pop_age = list((age+0.5)*DAYS_PER_YEAR for age in range(min_b_age, max_b_age+1))
        pop_date = list(to_epoch_days(datetime.date(year, self.enum_month, self.enum_day)) for year in range(min_b_date, max_b_date+1))

        # We add on a border of ages to the interpolation, to ensure that we have gridpoints all
        # along the boundaries.
        # FIXME: the old age border should not be necessary
        pop = np.vstack((pop[0:1,:],pop,pop[-2:-1, :]))
        pop_age = [self.base_model.get_age_range()[0]*DAYS_PER_YEAR]+pop_age+[(self.base_model.get_age_range()[1]+1)*DAYS_PER_YEAR-1]
                
        # This is an unnecessary check but may catch any bugs above
        if pop.shape != (len(pop_age), len(pop_date)):
            raise ValueError("Dimension of underlying does not match", pop.shape, (len(pop_age), len(pop_date)))
        
        # Create the actual spline fuction using numpy
        interp = RectBivariateSpline(pop_age, pop_date, pop)
        return interp
        
    def pop_age(self, date, region, sex, age):
        date = self.check_date(date)
        try:
            age = self.check_age(age)
        except ValueError:
            return 0

        model = self.get_model(region, sex)
        interp = model(age, date)
        return int(round(interp))

    def pop_sum_age(self, date, region, sex, age_from = None, age_to = None):
        date = self.check_date(date)
        age_from = self.check_age(age_from, "min", truncate=True)
        age_to = self.check_age(age_to, "max", truncate=True)
    
        model = self.get_model(region, sex)
        
        # Never want to access the function outside the interpolation points, so
        # for the edge case we adjust our integration bounds to avoid edge effects.
        if date - 0.1 < self.get_date_range()[0]:
            pop_sum = model.integral(age_from, age_to+1, date, date + 0.1)*10
        elif date + 0.1 > self.get_date_range()[1]:
            pop_sum = model.integral(age_from, age_to+1, date - 0.1, date)*10
        else:
            pop_sum = model.integral(age_from, age_to+1, date - 0.1, date + 0.1)*5
                
        return int(round(pop_sum))
        
    def pop_sum_dob(self, date, region, sex, dob_from = None, dob_to = None):
        age_from = date - dob_to if dob_to is not None else None
        age_to = date - dob_from if dob_from is not None else None
        return self.pop_sum_age(date, region, sex, age_from, age_to)
        





###################################################################################################
# MISC STUFF THAT COULD BE DELETED
###################################################################################################

class LinearToyPopulationModel(PopulationModel):
    '''
    A toy population model for testing only.
    '''
    
    def get_regions(self):
        return ["World"]
        
    def get_age_range(self):
        return (0,4)
        
    def get_sexes(self):
        return ["NA"]
        
    def get_date_range(self):
        return (20, 24)
        
    def pop_age(self, date, region, sex, age):
        date = self.check_date(date)
        try:
            age = self.check_age(age)
        except ValueError:
            return 0
                
        return (date - age) * 10000

class LinearDailyPopulationModel(DailyPopulationModel):
    '''
    A linear interpolation daily population model.
    WARNING: this code is probably buggy, I wrote it mainly as a speed benchmark, so it is not
    well checked & tested like the bicubic above. If we wanted linear interpolation it would be
    safer to modify the bicubic implementation by switching in numpy's linear interpolation function.
    '''
    def __init__(self, base_model):
        super(LinearDailyPopulationModel, self).__init__(base_model)
        self.base_min_date, self.base_max_date = self.base_model.get_date_range()
        self.base_min_age, self.base_max_age = self.base_model.get_age_range()
    
    def pop_age(self, date, region, sex, age):
        year, frac = self.get_enum_year_frac(date)
        age_years, age_frac = self.get_age_year_frac(age)
        
                
        if year >= self.base_min_date:
            low_year = year
        elif year == self.base_min_date - 1:
            low_year = year + 1
        else:
            raise ValueError("Low date too low", year, self.base_min_date)
            
        if year < self.base_max_date:
            high_year = year + 1
        elif year == self.base_max_date:
            high_year = year
        else:
            raise ValueError("High date too high", year, self.base_max_date)
            
        low_age = age_years
        if age_years < self.base_max_age:
            high_age = age_years + 1
        elif age_years == self.base_max_age:
            high_age = age_years
        else:
            return 0
            #raise ValueError("High age too high", age_years, self.base_max_age)
                
        # Evaluate the four corners of this grid square on the population surface
        low_year_low_age = self.base_model.pop_age(low_year, region, sex, low_age) / DAYS_PER_YEAR
        low_year_high_age = self.base_model.pop_age(low_year, region, sex, high_age) / DAYS_PER_YEAR
        high_year_low_age = self.base_model.pop_age(high_year, region, sex, low_age) / DAYS_PER_YEAR
        high_year_high_age = self.base_model.pop_age(high_year, region, sex, high_age) / DAYS_PER_YEAR
        
        
        interp_low_age = low_year_low_age * (1 - frac) + high_year_low_age * frac
        interp_high_age =  low_year_high_age * (1 - frac) + high_year_high_age * frac
        
        interp = interp_low_age * (1 - age_frac) + interp_high_age * age_frac


        return interp
        
    def pop_dob(self, date, region, sex, dob):
        year, frac = self.get_enum_year_frac(date)
        dob_year, dob_frac = self.get_enum_year_frac(dob)
        #print from_epoch_days(date), from_epoch_days(dob)
        #print dob_year, dob_frac

        # Evaluate the four corners of this grid square on the population surface
        low_year_low_dob = self.base_model.pop_dob(year, region, sex, dob_year) / DAYS_PER_YEAR
        low_year_high_dob = self.base_model.pop_dob(year, region, sex, dob_year+1) / DAYS_PER_YEAR
        high_year_low_dob = self.base_model.pop_dob(year+1, region, sex, dob_year) / DAYS_PER_YEAR
        high_year_high_dob = self.base_model.pop_dob(year+1, region, sex, dob_year+1) / DAYS_PER_YEAR
        
        interp_low_dob = low_year_low_dob + (high_year_low_dob - low_year_low_dob) * frac
        interp_high_dob =  low_year_high_dob + (high_year_high_dob - low_year_high_dob) * frac
        
        interp = interp_low_dob + (interp_high_dob - interp_low_dob) * dob_frac
        return round(interp)    

    def pop_sum_age(self, date, region, sex, age_from = None, age_to = None):
        age_range = self.get_age_range()
        if age_from is None:
            age_from = age_range[0]
        if age_to is None:
            age_to = age_range[1]
    
        date_year, date_frac = self.get_enum_year_frac(date)
        age_from_years, age_from_frac = self.get_age_year_frac(age_from)
        age_to_years, age_to_frac = self.get_age_year_frac(age_to)
        
        if age_from_frac == 0.0:
            first_part = 0
            second_part_start = age_from_years
        else:
            first_part = PopulationModel.pop_sum_age(self, date, region, sex, age_from, int((age_from_years + 1) * DAYS_PER_YEAR - 1))
            second_part_start = int((age_from_years + 1) * DAYS_PER_YEAR)
            
        if age_to_years > second_part_start:
            second_part_low = self.base_model.pop_sum_age(date_year, region, sex, second_part_start, age_to_years-1)
            second_part_high = self.base_model.pop_sum_age(date_year+1, region, sex, second_part_start, age_to_years-1)
            second_part = second_part_low * (1-date_frac) + second_part_high * date_frac
        else:
            second_part = 0
        
        if age_to_frac == 0.0:
            third_part = 0
        else:
            third_part = PopulationModel.pop_sum_age(self, date, region, sex, int(age_to_years * DAYS_PER_YEAR), age_to)
            
        return first_part + second_part + third_part
        
    def pop_sum_dob(self, date, region, sex, dob_from = None, dob_to = None):
        age_from = date - dob_to if dob_to is not None else None
        age_to = date - dob_from if dob_from is not None else None
        return self.pop_sum_age(date, region, sex, age_from, age_to)


        
    