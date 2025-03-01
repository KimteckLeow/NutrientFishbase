# FishBase_Nutrient_Predictions.py - Code to apply nutrient estimates for unobserved FishBase species
# Aaron MacNeil 30.04.2021

# Import python packages
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pymc3 as pm
import theano as T
import theano.tensor as tt
import scipy as sp
import pdb
import arviz as az

if __name__ == '__main__':
    # -------------------------------------------Helper functions------------------------------------------------------------- #

    def indexall(L):
        poo = []
        for p in L:
            if not p in poo:
                poo.append(p)
        Ix = np.array([poo.index(p) for p in L])
        return poo,Ix


    def subindexall(short,long):
        poo = []
        out = []
        for s,l in zip(short,long):
            if not l in poo:
                poo.append(l)
                out.append(s)
        return indexall(out)

    match = lambda a, b: np.array([ b.index(x) if x in b else None for x in a ])

    def plot_ppc_loopit(idata, title):
        fig = plt.figure(figsize=(12,9))
        ax_ppc = fig.add_subplot(211)
        ax1 = fig.add_subplot(223); ax2 = fig.add_subplot(224)
        az.plot_ppc(idata, ax=ax_ppc);
        for ax, ecdf in zip([ax1, ax2], (False, True)):
            az.plot_loo_pit(idata, y="Yi", ecdf=ecdf, ax=ax);
        ax_ppc.set_title(title)
        ax_ppc.set_xlabel("")
        return np.array([ax_ppc, ax1, ax2])

    # --------------------------------------Import data------------------------------------------------------------------ #
    # Species traits data
    sdata = pd.read_csv('https://raw.githubusercontent.com/mamacneil/NutrientFishbase/master/data/all_traits_for_predictions.csv')
    # Nutrients data
    ndata = pd.read_csv('https://raw.githubusercontent.com/mamacneil/NutrientFishbase/master/data/all_nutrients_active.csv')
    # Traits data
    tdata = pd.read_csv('https://raw.githubusercontent.com/mamacneil/NutrientFishbase/master/data/all_traits_active.csv')
    
    # List of nutrients
    nlist = pd.read_csv('Nutrient_list.csv')
    # --------------------------------------Merge data------------------------------------------------------------------ #

    # Add traits information to nutritional dataframe
    indx = match(ndata.spec_code.unique(),list(tdata.spec_code.values))
    rindx = match(ndata.spec_code,list(ndata.spec_code.unique()))

    # Traits to port over
    tmp = ['Class', 'Order', 'Family','Genus', 'DemersPelag','EnvTemp', 'DepthRangeDeep', 'trophic_level', 'Feeding_path', 'Lmax','BodyShape', 'K', 'tm', 'environment']

    # Port over
    for trait in tmp:
        ndata[trait] = tdata[trait].values[indx][rindx]
    
    # --------------------------------------Combine categories------------------------------ #
    #bathydemersal / demersal -> demersal
    ndata['DemersPelag'] = ndata['DemersPelag'].replace(['bathydemersal'],'demersal')
    #pelagic / pelagic_neritic / pelagic_oceanic -> pelagic
    ndata['DemersPelag'] = ndata['DemersPelag'].replace(['pelagic_neritic'],'pelagic')
    ndata['DemersPelag'] = ndata['DemersPelag'].replace(['pelagic_oceanic'],'pelagic')
    #benthopelagic    -> no change
    #reef_associated -> no change
    ndata['Feeding_path'] = [x+'_path' for x in ndata["Feeding_path"]]
    
    #bathydemersal / demersal -> demersal
    sdata['DemersPelag'] = sdata['DemersPelag'].replace(['bathydemersal'],'demersal')
    #pelagic / pelagic_neritic / pelagic_oceanic -> pelagic
    sdata['DemersPelag'] = sdata['DemersPelag'].replace(['pelagic_neritic'],'pelagic')
    sdata['DemersPelag'] = sdata['DemersPelag'].replace(['pelagic_oceanic'],'pelagic')
    sdata['DemersPelag'] = sdata['DemersPelag'].replace(['bathypelagic'],'pelagic')
    #benthopelagic    -> no change
    #reef_associated -> no change
    sdata['Feeding_path'] = [x+'_path' for x in sdata["Feeding_path"]]
    
    # --------------------------------------Grab zero-centering values------------------------------ #
    # MaxDepth
    MaxDepth_mu = np.mean(np.log(ndata['DepthRangeDeep'].values))
    # TL
    TL_mu = np.mean(ndata['trophic_level'].values)
    # Species maximum length
    LMax_mu = np.mean(np.log(ndata['Lmax'].values))
    # Growth coefficient
    K_mu = np.mean(ndata['K'].values)
    # Age at maturity
    tm_mu = np.mean(np.log(ndata['tm'].values))
    
    # --------------------------------------Loop over nutrients------------------------------------------------------------------ #
    # List available nutrients
    Nutrients =  nlist.Nutrient.values
    # Number of nutrients
    nnut = len(Nutrients)
    # Number of species to predict
    nspp = sdata.shape[0]
    print('Generating estimates for '+str(nspp)+' species:')
    
    # Output dataframe
    out = sdata[['species','spec_code']]

    # Loop over nutrients
    for i in range(nnut):
        # Grab nutrient
        nut = Nutrients[i]
        print('Generating '+nut+' estimates...')
        # Import posteriors
        REZ = pd.read_csv(nut+'_results.csv')
        
        # Empty arrays to hold predictive values
        xmu = np.empty(nspp)
        xl95 = np.empty(nspp)
        xl50 = np.empty(nspp)
        xu50 = np.empty(nspp)
        xu95 = np.empty(nspp)
        
        # Iterate over species
        for i in range(nspp):
            # Grab tratis for species i
            tmp = sdata.iloc[i]
            
            # Grab closest phylogenetic intercept
            if tmp.Genus in REZ.columns:
                REZ_I = REZ[tmp.Genus].values
            elif tmp.Family in REZ.columns:
                REZ_I = REZ[tmp.Family].values
            elif tmp.Order in REZ.columns:
                REZ_I = REZ[tmp.Order].values
            elif tmp.Class in REZ.columns:
                REZ_I = REZ[tmp.Class].values
            else:
                REZ_I = REZ['Intercept'].values
            
            # Calculate posterior predictions for species i
            μ_ = REZ_I+REZ[tmp['DemersPelag']].values+REZ[tmp['EnvTemp']].values+REZ[tmp['environment']].values+REZ['TL'].values*(tmp['trophic_level']-TL_mu)+REZ[tmp['Feeding_path']]+REZ['LMax'].values*(np.log(tmp['Lmax'])-LMax_mu)+REZ[tmp['BodyShape']].values+REZ['tm'].values*(np.log(tmp['tm'])-tm_mu)+REZ['wet'].values+REZ['muscle'].values
            
            if nut=='Protein':
                μ = μ_
            else:
                μ = np.exp(μ_)
            
            # Check for infinine estimates
            if np.isinf(np.median(μ)):
                xmu[i] = -1
                xl95[i] = -1
                xl50[i] = -1
                xu50[i] = -1
                xu95[i] = -1
            else:
                xmu[i] = max(np.median(μ),0)
                xl95[i] = max(np.percentile(μ,2.5),0)
                xl50[i] = max(np.percentile(μ,25),0)
                xu50[i] = max(np.percentile(μ,75),0)
                xu95[i] = max(np.percentile(μ,97.5),0)
        
        # --------------------------------------Export predictions------------------------------------------------------------------ #
        # Add nutrient predictions to output dataframe
        out[nut+'_mu'] = xmu
        out[nut+'_l95'] = xl95
        out[nut+'_l50'] = xl50
        out[nut+'_u50'] = xu50
        out[nut+'_u95'] = xu95
    
    # Write to dataframe
    out.to_csv('Species_Nutrient_Predictions.csv', index=False)
    print('Done')

    # --------------------------------------Compare observed and predicted------------------------------------------------------------------ #
    # List available nutrients
    Nutrients =  ndata.nutrient.unique()
    # Number of nutrients
    nnut = len(Nutrients)
    
    # Setup multipanel figure
    nrows, ncols = 3, 3
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(12,8))
    ax_ = axes.flatten()

    for i in range(nnut):
        # Subset target nutrient
        nut = Nutrients[i]
        tmpdata = ndata[ndata.nutrient==nut].copy()
        # Filter out zeros?
        #tmpdata = tmpdata[tmpdata.value!=0].copy()

        ax_[i].axvline(np.quantile(tmpdata.value,0.5))
        ax_[i].axvline(np.quantile(tmpdata.value,0.05),linestyle=':')
        ax_[i].axvline(np.quantile(tmpdata.value,0.95),linestyle=':')
        ax_[i].set_title(nut)
        ax_[i].hist(out[nut+'_mu'],bins=50)
        
    fig.tight_layout()
    fig.subplots_adjust(top=0.95)
    plt.savefig('Species_Obs_predictions.jpg',dpi=300)