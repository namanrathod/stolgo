import os
import requests
import concurrent.futures
import io

from datetime import datetime,timedelta
import pandas as pd
from pandas import ExcelWriter
from requests.exceptions import HTTPError
from bs4 import BeautifulSoup

from stolgo.nse_urls import NseUrls
from stolgo.helper import get_formated_date
from stolgo.request import RequestUrl

#default params for url connection
DEFAULT_TIMEOUT = 5 # seconds
MAX_RETRIES = 2

class NseData:
    def __init__(self,timeout=DEFAULT_TIMEOUT,max_retries=MAX_RETRIES):
        self.__nse_urls = NseUrls()
        self.__headers = self.__nse_urls.header
        #create request
        self.__request = RequestUrl()

    def get_indices(self):
        """To get list of NSE indices
        """
        try:
            index_page = self.__request.get(self.__nse_urls.INDEX_URL,headers=self.__headers)
            soup = BeautifulSoup(index_page.text,'lxml')
            table = soup.find("select",{"id":"indexType"})
            indices_data = table.find_all("option")
            indices = [index.get("value") for index in indices_data if "NIFTY" in index.get("value")]

            #lets append india vix as well
            indices.append("INDIA VIX")
            return indices
        except Exception as err:
            raise Exception("Error occurred while getting NSE indices :", str(err))

    def get_oc_exp_dates(self,symbol):
        
        """get current  available expiry dates

        :raises Exception: NSE connection related
        :return: expiry dates
        :rtype: list
        """        
        try:
            base_oc_url = self.__nse_urls.get_option_chain_url(symbol)
            page = self.__request.get(base_oc_url,headers=self.__headers)
            soup = BeautifulSoup(page.text,'lxml')
            table = soup.find("select",{"id":"date"})
            expiry_out = table.find_all("option")
            expiry_dates = [exp_date.get("value") for exp_date in expiry_out][1:]
            return expiry_dates

        except Exception as err:
            raise Exception("something went wrong while reading nse URL :", str(err))

    def get_option_chain_df(self, symbol, expiry_date,dayfirst=False):
        """ This function fetches option chain data from NSE and returns in pandas.DataFrame

        :param symbol: stock/index symbol
        :type symbol: string
        :param expiry_date: expiry date (all date formats accepted)
        :type expiry_date: string
        :param dayfirst: True if date format is european style DD/MM/YYYY, defaults to False
        :type dayfirst: bool, optional
        :raises Exception: NSE connection related
        :raises Exception: In html parsing
        :return: option chain
        :rtype: pandas.DataFrame
        """
        try:
            oc_url = self.__nse_urls.get_option_chain_url(symbol, expiry_date,dayfirst)
            # If the response was successful, no Exception will be raised
            oc_page = self.__request.get(oc_url, headers = self.__headers)

        except Exception as err:
             raise Exception("Error occured while connecting NSE :", str(err))
        else:
            try:
                dfs = pd.read_html(oc_page.text)
                return dfs[1]
            except Exception as err:
                raise Exception("Error occured while reading html :", str(err))

    def __get_file_path(self, file_name, file_path = None, is_use_default_name = True):
        """[summary]

        :param file_name: file name 
        :type file_name: string
        :param file_path: file directory or file path , defaults to None
        :type file_path: string, optional
        :param is_use_default_name: to get filename in current timestamp, defaults to True
        :type is_use_default_name: bool, optional
        :return: file path
        :rtype: string
        """
        try:
            if not file_path:
                file_path = os.getcwd()
            
            if os.path.isfile(file_path):
                if (not is_use_default_name):
                    return file_path
                # if need to use default file path, we get parent path
                else:
                    file_path = os.path.dirname(file_path)
                    
            # datetime object containing current date and time
            now = datetime.now()
            # dd/mm/YY H:M:S
            dt_string = now.strftime("%d_%B_%H_%M")
            file_name = file_name + "_" + dt_string + ".xlsx"
            
            excel_path = os.path.join(file_path, file_name)
            return excel_path
        except Exception as err:
            print("Error while naming file. Error: ", str(err))

    def get_option_chain_excel(self, symbol, expiry_date,dayfirst=False,file_path = None, is_use_default_name = True):
        """Fetches NSE option chain data and returns in the form of excel (.xlsx)

        :param symbol: stock/index symbol
        :type symbol: string
        :param expiry_date: expiry date (all date formats accepted)
        :type expiry_date: string
        :param dayfirst: True if date format is european style DD/MM/YYYY, defaults to False
        :type dayfirst: bool, optional
        :param file_path: file/folder path, defaults to None
        :type file_path: string, optional
        :param is_use_default_name:  to get filename as current timestamp, defaults to True
        :type is_use_default_name: bool, optional
        :raises Exception:  NSE connection related
        """        
        try:
            df = self.get_option_chain_df(symbol, expiry_date,dayfirst)
            file_name = symbol + "_" + expiry_date 
            excel_path = self.__get_file_path(file_name, file_path, is_use_default_name)
            
            writer = ExcelWriter(excel_path)
            df.to_excel(writer, file_name)
            writer.save()
        except Exception as err:
            raise Exception("Error occured while getting excel :", str(err))

    def __join_part_oi_dfs(self,df_join,df_joiner):
        """will append joiner to join for oi_dfs

        :param df_join: Dictionary of participants
        :type df_join: dict
        :param df_joiner: Dictionary of participants
        :type df_joiner: dict
        """        
        for client in df_join:
            df_join[client] = self.__join_dfs(df_join[client],df_joiner[client]).sort_index()

    def __join_dfs(self,join,joiner):
        """will append joiner to join for oi_dfs

        :param join: df which will be appended
        :type join: pandas.DataFrame
        :param joiner: df which we want to append
        :type joiner: pandas.DataFrame
        :return: merged data frame
        :rtype: pandas.DataFrame
        """        
        return join.append(joiner)

    def get_part_oi_df(self,start=None,end=None,periods=None,dayfirst=False,workers=None):
        """Return dictionary of participants containing data frames

        :param start: start date , defaults to None
        :type start: string, optional
        :param end: end date, defaults to None
        :type end: string, optional
        :param periods: number of days, defaults to None
        :type periods: interger, optional
        :param dayfirst: True if date format is european style DD/MM/YYYY, defaults to False
        :type dayfirst: bool, optional
        :param workers: Number of threads for requesting nse, defaults to None
        :type workers: interger, optional
        :raises Exception: NSE Connection/Request overload
        :return: participant wise open interest
        :rtype: pandas.DataFrame
        """
        try:
            #format date just in case
            if start:
                start = get_formated_date(start,dayfirst=dayfirst)
            if end:
                end = get_formated_date(end,dayfirst=dayfirst)

            #get urls for these days
            dates = pd.date_range(start=start,end=end, periods=periods,freq='B')
            url_date = [(self.__nse_urls.get_participant_oi_url(date),date) for date in dates]#

            oi_clm = self.__nse_urls.PART_OI_CLM
            #lets preinitialize, better readability
            oi_dfs = {  "Client":pd.DataFrame(columns=oi_clm,index=dates),
                        "DII":pd.DataFrame(columns=oi_clm,index=dates),
                        "FII":pd.DataFrame(columns=oi_clm,index=dates),
                        "Pro":pd.DataFrame(columns=oi_clm,index=dates),
                        "TOTAL":pd.DataFrame(columns=oi_clm,index=dates)
                        }

            if not workers:
                workers = os.cpu_count() * 2

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                responses = {executor.submit(self.__request.get, url,self.__headers): (url,date) for url,date in url_date}
                for res in concurrent.futures.as_completed(responses):
                    url,date = responses[res]
                    try:
                        csv = res.result()
                    except Exception as exc:
                        #might be holiday
                        pass
                    else:
                        df = pd.read_csv(io.StringIO(csv.content.decode('utf-8')))
                        #drop the first header
                        df_header = df.iloc[0]
                        #is there any implace way?
                        df = df[1:]
                        df.columns = df_header
                        df.set_index('Client Type',inplace=True)
                        #lets us create data frome for all client type
                        oi_dfs['Client'].loc[date] = df.loc['Client']
                        oi_dfs['FII'].loc[date] = df.loc['FII']
                        oi_dfs['DII'].loc[date] = df.loc['DII']
                        oi_dfs['Pro'].loc[date] = df.loc['Pro']
                        oi_dfs['TOTAL'].loc[date] = df.loc['TOTAL']

            if not oi_dfs['Client'].empty:
                #remove nan row
                for client in oi_dfs:
                    oi_dfs[client].dropna(inplace=True)

                #if holiday occured in business day, lets retrive more data equivalent to holdidays. 
                if oi_dfs['Client'].shape[0] < periods:
                    new_periods = periods - oi_dfs['Client'].shape[0]
                    try:
                        #if only start, find till today
                        if start and (not end):
                            s_from = oi_dfs['Client'].index[-1] + timedelta(1)
                            e_till = None
                        #if not start, can go to past
                        elif(end and (not start)):
                            s_from = None
                            e_till = oi_dfs['Client'].index[0] - timedelta(1)
                        #if start and end, no need to change
                        else:
                            return oi_dfs
                    except IndexError as err:
                        raise Exception("NSE Access error.size down/clean cookies to resolve the issue.")
                    except Exception as exc:
                        raise Exception("participant OI error: ",str(exc))

                    oi_dfs_new = self.get_part_oi_df(start = s_from,end = e_till,periods = new_periods)
                    self.__join_part_oi_dfs(oi_dfs,oi_dfs_new)

                return oi_dfs

        except Exception as err:
            raise Exception("Error occured while getting part_oi :", str(err))

    def __parse_indexdata(self,res_txt,symbol):
        dfs = pd.read_html(res_txt)[0]
        if "NIFTY" in symbol:
            fined_dfs = dfs.iloc[0:]
            fined_dfs.columns = self.__nse_urls.INDEX_DATA_CLM
        elif symbol == "INDIA VIX":
            fined_dfs = dfs.iloc[1:]
            fined_dfs.drop(fined_dfs.index[0],inplace=True)
            fined_dfs.columns = self.__nse_urls.VIX_DATA_CLM
        fined_dfs.drop(fined_dfs.index[-1],inplace=True)
        fined_dfs.set_index("Date",inplace=True)
        return fined_dfs

    def get_data(self,symbol,series="EQ",start=None,end=None,periods=None,dayfirst=False):
        """To get NSE stock data

        :param symbol: stock/index symbol
        :type symbol: string
        :param series: segment, defaults to "EQ"
        :type series: string, optional
        :param start: start date, defaults to None
        :type start: string, optional
        :param end: end date, defaults to None
        :type end: string, optional
        :param periods: number of days, defaults to None
        :type periods: interger, optional
        :param dayfirst: True if date format is european style DD/MM/YYYY, defaults to False
        :type dayfirst: bool, optional
        :raises Exception: NSE Connection Related
        :return: stock data
        :rtype: pandas.DataFrame
        """
        try:
            data_url = self.__nse_urls.get_stock_data_url\
                                                        (
                                                        symbol.upper(),series=series,start=start,
                                                        end=end,periods=periods,dayfirst=dayfirst
                                                        )

            csv = self.__request.get(data_url,headers=self.__headers)

            #if it is index, wee need to read table
            # Why the heck, We are doing so much handling? Is there any other way?
            # Suggestions are welcome. ping me on github
            if ("NIFTY" in symbol) or ("INDIA VIX" == symbol):
                dfs = self.__parse_indexdata(csv.text,symbol)
            else:
                dfs = pd.read_csv(io.StringIO(csv.content.decode('utf-8')))
                dfs.set_index('Date ',inplace=True)
            # Converting the index as date
            dfs.index = pd.to_datetime(dfs.index)

            if periods and (dfs.shape[0] < periods):
                new_periods = periods - dfs.shape[0]
                try:
                    #if only start, find till today
                    if start and (not end):
                        s_from = dfs.index[0] + timedelta(1)
                        e_till = None
                    #if not start, can go to past
                    elif(end and (not start)):
                        s_from = None
                        e_till = dfs.index[-1] - timedelta(1)
                    #if start and end, no need to change
                    else:
                        return dfs
                except IndexError as err:
                    raise Exception("NSE Access error.")
                except Exception as exc:
                    raise Exception("Stock data error: ",str(exc))
                dfs_new = self.get_data(symbol,series,start = s_from,end = e_till,periods = new_periods)
                dfs = self.__join_dfs(dfs,dfs_new).sort_index(ascending=False)

            return dfs

        except Exception as err:
            raise Exception("Error occured while fetching stock data :", str(err))