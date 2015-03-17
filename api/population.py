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

class PopulationModel(object):
    def get_regions(self):
        raise NotImplemented
        
    def get_age_range(self):
        raise NotImplemented
        
    def get_age_quantum(self):
        return 1
        
    def get_sexes(self):
        raise NotImplemented
        
    def get_date_range(self):
        raise NotImplemented
        
    def get_date_quantum(self):
        return 1
    
    def pop_age(self, date, region, sex, age):
        raise NotImplemented
        
    def pop_dob(self, date, region, sex, dob):
        #print "PD", date, region, sex, dob
        age = date - dob
        return self.pop_age(date, region, sex, age)
        
    def pop_integrate_age(self, date, region, sex, age_from = None, age_to = None):
        age_range = self.get_age_range()
        if age_from is None: # zero is a valid value
            age_from = age_range[0]
        if age_to is None:
            age_to = age_range[1]
           
        multiage_pop = 0
        for age in range(age_from, age_to+self.get_age_quantum(), self.get_age_quantum()):
            multiage_pop += self.pop_age(date, region, sex, age)
            
        return multiage_pop
        
    def pop_integrate_dob(self, date, region, sex, dob_from = None, dob_to = None):
        age_range = self.get_age_range()
        if dob_from is None: # zero may be a valid value
            dob_from = date - age_range[1]
        if dob_to is None:
            dob_to = date - age_range[0]
            
        multidob_pop = 0
        for dob in range(dob_from, dob_to+self.get_date_quantum(), self.get_date_quantum()):
            multidob_pop += self.pop_dob(date, region, sex, dob)
        
        return multidob_pop

    # Find the date when the population born after dob_from is equal to pop
    def pop_integrate_dob_inverse_date(self, pop, region, sex, dob_from):
        date_lower = dob_from
        date_upper = self.get_date_range()[1]
        pop_lower = self.pop_integrate_dob(date_lower, region, sex, dob_from, date_lower)
        pop_upper = self.pop_integrate_dob(date_upper, region, sex, dob_from, date_upper)
        
        def midpoint(lower, upper):
            return lower + (upper - lower) / 2
        
        while date_upper - date_lower > self.get_date_quantum():   
            date_midpoint = midpoint(date_lower, date_upper)
            pop_midpoint = self.pop_integrate_dob(date_midpoint, region, sex, dob_from, date_midpoint)
            #print 'd',date_lower, date_midpoint, date_upper
            #print 'p',pop_lower, pop_midpoint, pop_upper
            if pop_midpoint < pop:
                date_lower, pop_lower = date_midpoint, pop_midpoint
            else:
                date_upper, pop_upper = date_midpoint, pop_midpoint
                
        return date_lower
        
    # date, region, sex can be:
    #  single <group> - return population for that <group>
    #  [<group1>,<group2>,...] - return population for each of those <groups>
    #
    # age, dob can be:
    #  single age - return population for that age
    #  [ages1, age2] - return population for each of those ages
    #  (age_min, age_max) - return population sum for this age range
    def pop(self, date, region, sex, age = None, dob = None):
        if age and dob:
            raise ValueError("must specify exactly one of age, dob")
                
class NpSingleYearPopulationModel(PopulationModel):
    def _age_index(self,age):
        return int(age)-self.age_range[0]
        
    def _date_index(self,date):
        return int(date)-self.date_range[0]
        
    def __init__(self, filename, check_or_create_pickle = False):
        self.age_range = (0, 100)
        self.date_range = (1950,2100)
        self.sexes = ('M','F')
        self.arrays = None
        if check_or_create_pickle and os.path.isfile(filename + ".pickle"):
            with open(filename + ".pickle", "rb") as file:
                self.arrays = pickle.load(file)
        else:
            self.load_pop_csv(filename)
            if check_or_create_pickle:
                with open(filename + ".pickle", "wb") as file:
                    pickle.dump(self.arrays, file)
        

        self.arrays = dict(self.arrays)

    def load_pop_csv(self, filename):
        self.arrays = defaultdict(lambda: defaultdict(lambda: np.empty((self.age_range[1]-self.age_range[0]+1, self.date_range[1]-self.date_range[0]+1))))

        with open(filename, 'r') as file:
            reader = csv.DictReader(file)
            # ?, LocID, Location (Country), VarID, Variant, Time, Age, pop male, pop female, pop total

            for row in reader:
                loc_dict = self.arrays[row['Location']]
                loc_dict['M'][self._age_index(row['Age']), self._date_index(row['Time'])] = round(float(row['PopMale'])*1000)
                loc_dict['F'][self._age_index(row['Age']),self._date_index(row['Time'])] = round(float(row['PopFemale'])*1000)

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
        if age < self.get_age_range()[0] or age > self.get_age_range()[1]:
            return 0
        
        return self.arrays[region][sex][self._age_index(age),self._date_index(date)]
        

DAYS_PER_YEAR = 365.25
EPOCH = datetime.date(1970, 1, 1)

def to_epoch_days(date):
    return (date - EPOCH).days
    
def from_epoch_days(days):
    delta = datetime.timedelta(days = days)
    return EPOCH + delta

def days_to_decimal_year(days):
    date = from_epoch_days(days)
    
    year = date.year
    year_start = datetime.date(year, 1, 1)
    year_start_days = to_epoch_days(year_start)
    year_end = datetime.date(year, 12, 31)
    year_length = (year_end - year_start).days

    frac = (days - year_start_days) / float(year_length) # force float division
    return year, frac

def decimal_year_to_days(year, frac):
    year_start = datetime.date(year, 1, 1)
    year_start_days = to_epoch_days(year_start)
    year_end = datetime.date(year, 12, 31)
    year_length = (year_end - year_start).days

    days = year_start_days + frac * year_length
    return days

class DailyPopulationModel(PopulationModel):        
    def __init__(self, base_model):
        self.base_model = base_model

    def get_regions(self):
        return self.base_model.get_regions()
        
    def get_age_range(self):
        min_years, max_years = self.base_model.get_age_range()
        return (int(min_years * DAYS_PER_YEAR), int(max_years * DAYS_PER_YEAR))
        
    def get_sexes(self):
        return self.base_model.get_sexes()
        
    def get_date_range(self):
        min_year, max_year = self.base_model.get_date_range()
        min_days = to_epoch_days(datetime.date(min_year, 7, 1))
        max_days = to_epoch_days(datetime.date(max_year, 7, 1))
        return (min_days, max_days)
    
    def get_midpoint_year_frac(self,date):
        year, frac = days_to_decimal_year(date)
        # Adjust frac since estimates are treated as midpoint
        if frac > 0.5:
            frac = frac - 0.5
        else:
            frac = frac + 0.5
            year = year - 1
        
        return year, frac
        
    def get_age_year_frac(self, age):
        age_years_float = age / DAYS_PER_YEAR
        age_years = int(age_years_float)
        age_frac = age_years_float - age_years
        return age_years, age_frac

class LinearDailyPopulationModel(DailyPopulationModel):
    def __init__(self, base_model):
        super(LinearDailyPopulationModel, self).__init__(base_model)
    
    def pop_age(self, date, region, sex, age):
        year, frac = self.get_midpoint_year_frac(date)
        age_years, age_frac = self.get_age_year_frac(age)
        
        # Evaluate the four corners of this grid square on the population surface
        low_year_low_age = self.base_model.pop_age(year, region, sex, age_years) / DAYS_PER_YEAR
        low_year_high_age = self.base_model.pop_age(year, region, sex, age_years+1) / DAYS_PER_YEAR
        high_year_low_age = self.base_model.pop_age(year+1, region, sex, age_years) / DAYS_PER_YEAR
        high_year_high_age = self.base_model.pop_age(year+1, region, sex, age_years+1) / DAYS_PER_YEAR
        
        interp_low_age = low_year_low_age + (high_year_low_age - low_year_low_age) * frac
        interp_high_age =  low_year_high_age + (high_year_high_age - low_year_high_age) * frac
        
        interp = interp_low_age + (interp_high_age - interp_low_age) * age_frac
        return round(interp)
        
    def pop_dob(self, date, region, sex, dob):
        year, frac = self.get_midpoint_year_frac(date)
        dob_year, dob_frac = self.get_midpoint_year_frac(dob)
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

    def pop_integrate_age(self, date, region, sex, age_from = None, age_to = None):
        age_range = self.get_age_range()
        if age_from is None:
            age_from = age_range[0]
        if age_to is None:
            age_to = age_range[1]
    
        date_year, date_frac = self.get_midpoint_year_frac(date)
        age_from_years, age_from_frac = self.get_age_year_frac(age_from)
        age_to_years, age_to_frac = self.get_age_year_frac(age_to)
        
        if age_from_frac == 0.0:
            first_part = 0
            second_part_start = age_from_years
        else:
            first_part = PopulationModel.pop_integrate_age(self, date, region, sex, age_from, int((age_from_years + 1) * DAYS_PER_YEAR - 1))
            second_part_start = int((age_from_years + 1) * DAYS_PER_YEAR)
            
        if age_to_years > second_part_start:
            second_part_low = self.base_model.pop_integrate_age(date_year, region, sex, second_part_start, age_to_years-1)
            second_part_high = self.base_model.pop_integrate_age(date_year+1, region, sex, second_part_start, age_to_years-1)
            second_part = second_part_low * (1-date_frac) + second_part_high * date_frac
        else:
            second_part = 0
        
        if age_to_frac == 0.0:
            third_part = 0
        else:
            third_part = PopulationModel.pop_integrate_age(self, date, region, sex, int(age_to_years * DAYS_PER_YEAR), age_to)
            
        return first_part + second_part + third_part
        
    def pop_integrate_dob(self, date, region, sex, dob_from = None, dob_to = None):
        age_from = date - dob_to if dob_to is not None else None
        age_to = date - dob_from if dob_from is not None else None
        return self.pop_integrate_age(date, region, sex, age_from, age_to)

class Spline2DDailyPopulationModel(DailyPopulationModel):        
    def __init__(self, base_model):
        super(Spline2DDailyPopulationModel, self).__init__(base_model)
        self.models = defaultdict(lambda: dict())
    
    def get_model(self, region, sex):
        try:
            return self.models[region][sex]
        except KeyError:
            self.models[region][sex] = self.build_model(region, sex)
            return self.models[region][sex]
            
    def build_model(self, region, sex):
        # bad encapsulation - can do better
        pop = self.base_model.arrays[region][sex] / float(DAYS_PER_YEAR)
        pop = np.vstack((pop[0:1,:],pop))
        # self._age_index(row['Age']), self._date_index(row['Time'])
        pop_age = list((age+0.5)*DAYS_PER_YEAR for age in range(self.base_model.get_age_range()[0], self.base_model.get_age_range()[1]+self.base_model.get_age_quantum(), self.base_model.get_age_quantum()))
        pop_age = [self.base_model.get_age_range()[0]*DAYS_PER_YEAR]+pop_age
        pop_date = list(to_epoch_days(datetime.date(year, 6, 30)) for year in range(self.base_model.get_date_range()[0], self.base_model.get_date_range()[1]+self.base_model.get_date_quantum(), self.base_model.get_date_quantum()))
        
        if pop.shape != (len(pop_age), len(pop_date)):
            raise ValueError("Dimension of underlying does not match", pop.shape, (len(pop_age), len(pop_date)))
        
        interp = RectBivariateSpline(pop_age, pop_date, pop)
        return interp
        
    def pop_age(self, date, region, sex, age):
        model = self.get_model(region, sex)
        interp = model(age, date)
        return round(interp)

    def pop_integrate_age(self, date, region, sex, age_from = None, age_to = None):
        age_range = self.get_age_range()
        if age_from is None:
            age_from = age_range[0]
        if age_to is None:
            age_to = age_range[1]
    
        model = self.get_model(region, sex)
        #print list(model(age/10.0, date) for age in range(age_from*10, age_to*10))
        sum = model.integral(age_from, age_to+1, date - 0.1, date + 0.1)*5
        return sum
        
    def pop_integrate_dob(self, date, region, sex, dob_from = None, dob_to = None):
        age_from = date - dob_to if dob_to is not None else None
        age_to = date - dob_from if dob_from is not None else None
        return self.pop_integrate_age(date, region, sex, age_from, age_to)
        

import population_original
class OriginalDailyPopulationModel(DailyPopulationModel):
    sexmap = {'M': 'male', 'F': 'female'}

    def __init__(self, base_model):
        super(OriginalDailyPopulationModel, self).__init__(base_model)
            
    def pop_age(self, date, region, sex, age):
        raise NotImplemented
        
    def pop_integrate_dob(self, date, region, sex, dob_from = None, dob_to = None):
        if dob_to is not None:
            raise NotImplemented("Not implemented for the general case")
                
        return population_original.worldPopulationRankByDate(
            self.sexmap[sex],
            region,
            from_epoch_days(dob_from),
            from_epoch_days(date)
        )

    def pop_integrate_dob_inverse_date(self, pop, region, sex, dob_from):
        return to_epoch_days(population_original.dateByWorldPopulationRank(
            self.sexmap[sex],
            region,
            from_epoch_days(dob_from),
            pop
        ))


    

start_time = time.time()
def elapsed():
    global start_time
    new_time = time.time()
    out = str(round(new_time - start_time,4)) + " s"
    start_time = new_time
    return out

def test_interp():
    pop2 = NpSingleYearPopulationModel("../data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv", check_or_create_pickle=True)
    pop_day = LinearDailyPopulationModel(pop2)
    pop_int = Spline2DDailyPopulationModel(pop2)
    pop_org = OriginalDailyPopulationModel(pop2)
    
    # Precache for 2D spline model
    pop_int.build_model("Australia", "M")
    pop_int.build_model("World", "M")
    
    # Precache for pop_org model
    population_original.dataStore.getOrGenerateExtrapolationTable("male","World")
    population_original.dataStore.getOrGenerateExtrapolationTable("male","Australia")    
 
    elapsed()

    print pop_day.pop_age(to_epoch_days(datetime.date(2010, 1, 1)), "Australia", "M", 19*365.25), elapsed() 
    print pop_int.pop_age(to_epoch_days(datetime.date(2010, 1, 1)), "Australia", "M", 19*365.25), elapsed()
    
    dob = to_epoch_days(datetime.date(1971,3,16))
    date = to_epoch_days(datetime.date(2020,10,2))
    print pop_day.pop_integrate_dob(date,"World","M",dob,None), elapsed()
    print pop_int.pop_integrate_dob(date,"World","M",dob,None), elapsed()
    print PopulationModel.pop_integrate_dob(pop_int, date,"World","M",dob,None), elapsed()
    print pop_org.pop_integrate_dob(date,"World","M",dob,None), elapsed()

    print from_epoch_days(pop_day.pop_integrate_dob_inverse_date(5e9, "World", "M", to_epoch_days(datetime.date(1981,10,28)))), elapsed()
    print from_epoch_days(pop_int.pop_integrate_dob_inverse_date(5e9, "World", "M", to_epoch_days(datetime.date(1981,10,28)))), elapsed()
    print from_epoch_days(pop_org.pop_integrate_dob_inverse_date(5e9, "World", "M", to_epoch_days(datetime.date(1981,10,28)))), elapsed()


def compare_original():
    #import algorithms

    pop2 = NpSingleYearPopulationModel("../data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv", check_or_create_pickle=True)
    pop_day = LinearDailyPopulationModel(pop2)
    
    #print algorithms.worldPopulationRankByDate("M", "World", datetime.date(1981,20,18), datetime.date(2015,3,14)), elapsed()
    print pop_day.pop_integrate_dob(to_epoch_days(datetime.date(2015,3,14)),"World","M",to_epoch_days(datetime.date(1981,10,28)),None)
    print pop_day.pop_integrate_dob(to_epoch_days(datetime.date(2015,3,14)),"Australia","F",to_epoch_days(datetime.date(2010,1,1)),None)
        
import sys 
if __name__ == "__main__":
    test_interp()
    #compare_original()
    sys.exit(0)

#    pop = SingleYearPopulationModel("../data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv")
    pop2 = NpSingleYearPopulationModel("../data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv", check_or_create_pickle=True)
    pop_day = LinearDailyPopulationModel(pop2)


    #print pop2.pop_integrate_age(2014, "Australia", "M"), elapsed()
    #print pop_day.pop_integrate_age(2014, "Australia", "M"), elapsed()
    
    #print pop_day.pop_integrate_age(2014, "Australia", "M", int(2.5*DAYS_PER_YEAR), int(10*DAYS_PER_YEAR))
    #print PopulationModel.pop_integrate_age(pop_day, 2014, "Australia", "M", int(2.5*DAYS_PER_YEAR), int(10*DAYS_PER_YEAR))

    #print pop2.pop_integrate_age(2014, "Australia", "M", 0, 0), elapsed()
    #print pop_day.pop_integrate_age(to_epoch_days(datetime.date(2014,7,1)), "Australia", "M", int(0*DAYS_PER_YEAR), int(1*DAYS_PER_YEAR)), elapsed()
    #print PopulationModel.pop_integrate_age(pop_day, to_epoch_days(datetime.date(2014,7,1)), "Australia", "M", int(0*DAYS_PER_YEAR), int(1*DAYS_PER_YEAR)), elapsed()
    #print sum(pop_day.pop_age(to_epoch_days(datetime.date(2014,7,1)), "Australia", "M", age) for age in range(0,365))

    print pop2.pop_integrate_dob(2014, "Australia", "M"), elapsed()
    print PopulationModel.pop_integrate_dob(pop_day, to_epoch_days(datetime.date(2014,6,30)), "Australia", "M"), elapsed()
    print pop_day.pop_integrate_dob(to_epoch_days(datetime.date(2014,6,30)), "Australia", "M"), elapsed()

    print pop2.pop_integrate_dob_inverse_date(3000000000, "World", "M", 1981), elapsed()
    print from_epoch_days(pop_day.pop_integrate_dob_inverse_date(3000000000, "World", "M", to_epoch_days(datetime.date(1981,10,28)))), elapsed()
    
    sys.exit(0)
    #print pop_day.pop_age(to_epoch_days(datetime.date(2010, 6, 15)), "Australia", "M", 19*365.25), elapsed() 
    #print pop_day.pop_dob(to_epoch_days(datetime.date(2010, 6, 15)), "Australia", "M", to_epoch_days(datetime.date(1991, 9, 15))), elapsed()
    #print PopulationModel.pop_dob(pop_day, to_epoch_days(datetime.date(2010, 6, 15)), "Australia", "M", to_epoch_days(datetime.date(1991, 9, 15))), elapsed()

    print pop2.pop_integrate_dob_inverse_date(3000000000, "World", "M", 1981), elapsed()
    print from_epoch_days(pop_day.pop_integrate_dob_inverse_date(3000000000, "World", "M", to_epoch_days(datetime.date(1981,1,1)))), elapsed()

    #print pop.pop_dob(2010, "Australia", "M", 1981)
    #print pop.pop_integrate_age(2014, "Australia", "M")
    #print PopulationModel.pop_integrate_age(pop,2014, "Australia", "M")
        
    