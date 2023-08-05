import json

import pandas as pd
import geopandas as gpd
import plotly.graph_objects as go

PATH_FANTOIR_VOIES = "./fantoir/voies.txt"
PATH_FANTOIR_COMMUNES = "./fantoir/communes.txt"
PATH_TYPE_VOIE_LOOKUP = "./type_voie_lookup.json"
PATH_COMMUNES_SHP = "./communes/communes.shp"


def parse_fantoir_communes(path=PATH_FANTOIR_COMMUNES):
    communes = dict()
    with open(path) as f:
        for line in f:
            insee = line[:2] + line[3:6]
            commune = line[11:33].strip()
            communes[insee] = commune
    return communes


def parse_fantoir_voies(communes, path=PATH_FANTOIR_VOIES):
    with open(PATH_TYPE_VOIE_LOOKUP) as f:
        type_voie_lookup = json.load(f)

    records = []
    with open(path) as f:
        for line in f:
            type_voie = type_voie_lookup[line[11:15].strip()]
            nom_voie = line[15:33].strip()
            insee = line[:2] + line[3:6]
            records.append(
                {
                    "insee": insee,
                    "commune": communes[insee],
                    "type_voie": type_voie,
                    "nom_voie": nom_voie,
                    "mot_voie": line[112:].strip(),
                }
            )
    df = pd.DataFrame.from_records(records)
    df["type_voie"] = df["type_voie"].apply(lambda x: x.capitalize())
    return df


def parse_communes_shp(path=PATH_COMMUNES_SHP):
    gdf = gpd.read_file(path)
    gdf = gdf.rename(
        columns={
            "NOM": "commune",
            "INSEE_COM": "insee",
            "POPULATION": "population",
        }
    )
    gdf = gdf[["commune", "insee", "population", "geometry"]]
    return gdf


def camembert_voies(
    voies,
    type_voie="Avenue",
    pull_offset=0.5,
    commune=None,
    insee=None,
):
    if commune:
        g = voies.loc[voies["commune"] == commune.upper()]
    elif insee:
        g = voies.loc[voies["insee"] == insee]
    else:
        g = voies
    length = len(g)
    g = g.groupby("type_voie", as_index=False).count()
    g["voie"] = "Autre"
    g.loc[g["nom_voie"] >= 0.01 * length, "voie"] = g["type_voie"]
    pull = [pull_offset if el else 0 for el in list(g.type_voie == type_voie)]
    fig = go.Figure(data=[go.Pie(values=g["nom_voie"], labels=g["voie"], pull=pull)])
    fig.show()


def analyse_type_voie(
    voies,
    communes,
    type_voie="Avenue",
    commune=None,
    nb_top=10,
    type_analyse="pourcentage",
    verbose=True,
):
    voies_dinteret = (
        voies.loc[voies["type_voie"] == type_voie]
        .groupby(["insee"])["nom_voie"]
        .count()
        .rename("compte_voies")
    )

    toutes_voies = (
        voies.groupby(["insee"])["nom_voie"].count().rename("compte_toutes_voies")
    )

    d = pd.concat([voies_dinteret, toutes_voies], axis=1)

    # Certaines communes ne contiennent aucune voie de type `type_voie`,
    # et ont donc des NaN dans la colonne `compte_voies`
    d.fillna(0, inplace=True)

    d["pourcentage_voies"] = d["compte_voies"] / d["compte_toutes_voies"]

    if type_analyse == "pourcentage":
        sortby = ["pourcentage_voies", "compte_toutes_voies"]
    else:
        sortby = ["compte_voies", "compte_toutes_voies"]

    if verbose:
        # On retire les communes avec trop peu de voies
        dd = d.loc[d.compte_toutes_voies >= 10].sort_values(by=sortby)

        i = 1
        print(f"Top {nb_top} des communes avec le plus de voies de type {type_voie}:")
        for insee, series in (
            dd.tail(nb_top).sort_values(by=sortby, ascending=False).iterrows()
        ):
            nom_complet_commune = f"{communes[insee].title()} ({insee[:2]})"
            print(
                f"{i:>2}. {nom_complet_commune:<29} — {series.pourcentage_voies*100:.2f}% "
                f"({int(series.compte_voies):>4} / {int(series.compte_toutes_voies):<4})"
            )
            i += 1

        if commune:
            print()
            insee = None
            for key, value in communes.items():
                if value == commune.upper():
                    insee = key

            if not insee:
                print(f"Erreur : La commune {commune} n'a pas de code INSEE")
                return

            pourcentage = d.loc[d.index == insee].pourcentage_voies.values[0]

            classement = list(dd.index).index(insee) / len(dd)

            print(
                f"La commune {commune} a {pourcentage*100:.2f}% de voies de type {type_voie}.\n"
                f"Elle se classe dans le top {(1-classement)*100:.2f}% des communes françaises "
                f"avec le plus de voies de type {type_voie}, sur {len(dd)} communes en tout."
            )

    return d.sort_values(by=sortby).reset_index()


def merge_voies_communes(voies, communes, communes_shp):
    # Ajout du nombre total de voies par commune
    d = (
        voies.groupby("insee", as_index=False)["nom_voie"]
        .count()
        .rename(columns={"nom_voie": "nb_voies"})
    )
    mdf = pd.merge(left=communes_shp, right=d, on="insee")

    # Ajout du type de voie prédominant par commune
    # Trick taken from https://stackoverflow.com/a/67007919
    d = (
        voies.groupby(["insee"])["type_voie"]
        .value_counts()
        .rename("count")
        .reset_index()
        .drop_duplicates("insee")
        .rename(columns={"type_voie": "voie_predominante"})[
            ["insee", "voie_predominante"]
        ]
    )
    mdf = pd.merge(left=mdf, right=d, on="insee")

    # Ajout du compte/pourcentage de certains types de voie
    for type_voie in [
        "Allee",
        "Avenue",
        "Boulevard",
        "Chemin",
        "Cite",
        "Cours",
        "Levee",
        "Place",
        "Promenade",
        "Quai",
        "Route",
        "Rue",
        "Square",
        "Villa",
    ]:
        dd = analyse_type_voie(voies, communes, type_voie=type_voie, verbose=False)[
            ["insee", "compte_voies", "pourcentage_voies"]
        ].rename(
            columns={
                "compte_voies": f"compte_{type_voie}",
                "pourcentage_voies": f"pourcentage_{type_voie}",
            }
        )
        mdf = pd.merge(left=mdf, right=dd, on="insee")

    for mot in [
        "mouette",
        "vigne",
        "chataign",
        "paris",
    ]:
        ddd = voies.loc[voies.nom_voie.apply(lambda x: mot.upper() in x)][
            ["insee"]
        ].drop_duplicates("insee")
        ddd[f"voie_contient_{mot}"] = True
        mdf = pd.merge(left=mdf, right=ddd, on="insee", how="outer")

    mdf.to_file("communes.fgb", driver="FlatGeobuf", index=False)


def plot_population_vs_nb_voies(voies, communes_shp):
    voies_grouped = (
        voies.groupby(["insee"], as_index=False)["nom_voie"]
        .count()
        .rename(columns={"nom_voie": "compte_toutes_voies"})
    )
    merged = pd.merge(left=communes_shp, right=voies_grouped, on="insee")
    fig = go.Figure(
        data=[
            go.Scatter(
                x=merged["population"],
                y=merged["compte_toutes_voies"],
                text=merged["commune"],
                mode="markers",
            )
        ]
    )
    fig.show()
