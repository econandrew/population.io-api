import unittest
import population
import datetime
import math
import random
import traceback
from tabulate import tabulate
from collections import defaultdict, OrderedDict

class TestDailyPopulationModel(unittest.TestCase):
    # Some unit tests that compare the interpolated tables with (i) the base table and (ii) the original 'oracle' implementation.
    # Some of these tests are not actually pass/fail 'tests', they just output tables of err %

    def setUp(self):
        # Create the three population models
        self.pop_year = population.NpSingleYearPopulationModel("../data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv", check_or_create_pickle=True)
        self.pop_day = population.BicubicSplineDailyPopulationModel(self.pop_year)
        self.pop_oracle = population.OriginalDailyPopulationModel(self.pop_year)

    def test_dimensions(self):
        # Test that the dimensions of pop_day match the oracle
        # This actually tests nothing right now as they both inherit from the same base as implemented currently
        self.assertEqual(self.pop_day.get_regions(), self.pop_oracle.get_regions())
        self.assertEqual(self.pop_day.get_sexes(), self.pop_oracle.get_sexes())
        self.assertEqual(self.pop_day.get_age_range(), self.pop_oracle.get_age_range())
        self.assertEqual(self.pop_day.get_date_range(), self.pop_oracle.get_date_range())

    def test_knots(self):
        # Test that pop_day at least reproduces the original (uninterpolated) data points within limits
        min_year, max_year = self.pop_year.get_date_range()
        min_age_year, max_age_year = self.pop_year.get_age_range()
        sexes = self.pop_year.get_sexes()
        regions = self.pop_year.get_regions()

        table = list()
        for region in regions:
            for sex in sexes:
                err_pc_max = float("-inf")
                err_pc_allage_max = float("-inf")
                err_sum_pc_max = float("-inf")
                for year in range(min_year, max_year+1):
                    err_sum = 0
                    year_pop_allage = self.pop_year.pop_sum_age(year, region, sex)
                    date_days = population.to_epoch_days(datetime.date(year, 7, 1))

                    for age_years in range(min_age_year, max_age_year+1):
                        age_days_low = int(age_years * population.DAYS_PER_YEAR)
                        age_days_high = int((age_years + 1) * population.DAYS_PER_YEAR - 1)

                        year_pop = self.pop_year.pop_age(year, region, sex, age_years)
                        day_pop = self.pop_day.pop_sum_age(date_days, region, sex, age_days_low, age_days_high)

                        err = abs(day_pop - year_pop) # won't handle zero pop - that's ok
                        err_pc =  err / float(year_pop)
                        err_pc_allage = err / float(year_pop_allage)
                        err_sum += err

                        err_pc_allage_max = max(err_pc_allage_max, err_pc_allage)
                        err_pc_max = max(err_pc_max, err_pc)

                    err_sum_pc = err_sum / year_pop_allage
                    err_sum_pc_max = max(err_sum_pc_max, err_sum_pc)

                table += [OrderedDict([
                    ('region', region),
                    ('sex', sex),
                    ('max pyramid err %', round(err_sum_pc_max*100,2)),
                    ('max hybrid err %', round(err_pc_allage_max*100,2)),
                    ('max entry err %', round(err_pc_max*100, 2))
                ])]

        print(tabulate(table, headers="keys"))
                
    def test_milestones_oracle(self):
        # Test that various milestones line up closely for the new and old implementations
        min_year, max_year = self.pop_year.get_date_range()
        min_age_year, max_age_year = self.pop_year.get_age_range()
        sexes = self.pop_year.get_sexes()
        regions = self.pop_year.get_regions()
        
        table = list()
        for region in random.sample(regions, 5):
            for sex in sexes:
                err_max = float("-inf")
                total_ex_both = 0
                total_ex_day = 0
                total_ex_oracle = 0
                total = 0

                dob_from = population.to_epoch_days(datetime.date(1970,1,1))
                #min_pop = self.pop_year.pop_sum_age(self.pop_year.get_date_range()[0], region, sex)
                max_pop = self.pop_year.pop_sum_age(self.pop_year.get_date_range()[1], region, sex)
                for milestone in random.sample(range(0, max_pop, int((max_pop - 0)/5)), 4): # all but the last
                    #print region, sex, milestone
                    try:
                        day_pop = self.pop_day.pop_sum_dob_inverse_date(milestone, region, sex, dob_from)
                        exception_day = False
                    except Exception as e:
                        exception_day = True

                    try:
                        oracle_pop = self.pop_oracle.pop_sum_dob_inverse_date(milestone, region, sex, dob_from)
                        exception_oracle = False
                    except Exception as e:
                        exception_oracle = True
                        
                    if exception_day and exception_oracle:
                        total_ex_both += 1
                    elif exception_day:
                        total_ex_day +=1
                    elif exception_oracle:
                        total_ex_oracle +=1
                    else:
                        err = abs(day_pop - oracle_pop) # won't handle zero pop - that's ok
                        err_max = max(err_max, err)
                    total += 1

                                    
                table += [OrderedDict([
                    ('region', region),
                    ('sex', sex),
                    ('max err (days)', err_max),
                    ('ex (both)', total_ex_both),
                    ('ex (day)', total_ex_day),
                    ('ex (orc)', total_ex_oracle),
                    ('total', total)
                ])]
                
        print(tabulate(table, headers="keys"))
        
# def plot_milestones_oracle(region, sex, dob):
#     pop_year = population.NpSingleYearPopulationModel("../data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv", check_or_create_pickle=True)
#     pop_day = population.BicubicSplineDailyPopulationModel(pop_year)
#     pop_oracle = population.OriginalDailyPopulationModel(pop_year)
#
#     import pylab
#     dob_days = population.to_epoch_days(dob)
#     days = range(dob_days, int(dob_days+100*population.DAYS_PER_YEAR), 30)
#     day_ranks = [pop_day.pop_sum_dob(d, region, sex, dob_days, d) for d in days]
#     oracle_ranks = [pop_oracle.pop_sum_dob(d, region, sex, dob_days, d) for d in days]
#     pylab.plot(day_ranks, oracle_ranks)
        
if __name__ == '__main__':
    unittest.main()
