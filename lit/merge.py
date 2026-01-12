import marimo

__generated_with = "0.16.0"
app = marimo.App(width="medium")

with app.setup:
    import marimo as mo
    import pandas as pd


@app.cell
def _():
    # list of csv files to read
    csv_files = [
        "gualandi12.csv",
        "heule22.csv",
        "hoeve21-table3.csv", # TODO falta os tempos
        "jabrayilov18.csv",
        "jabrayilov22.csv",
        "malaguti11.csv",
        #"morrison16.csv", # Eles discartam alguns tempos, tenho que conferir o paper
        "ternier17.csv", # TODO faltar marcar os LB (enumeração)
    ]
    return (csv_files,)


@app.cell
def _():
    held = read_csv("../../logs/held.csv")
    held["source"] = "held"
    return (held,)


@app.function
def read_csv(file:str):
    """Read a CSV file and return a DataFrame."""
    #print(file)
    df = pd.read_csv(file)
    #print(df)
    # remove every column that is not 'instance', 'lb', 'ub', 'time'
    # some might not have the 'lb' column
    if 'lb' not in df.columns:
        df['lb'] = None
    df = df[['instance', 'lb', 'ub', 'time']]
    # write 'source' as file.replace('csv', '')
    df['source'] = file.replace('.csv', '')
    # transform 'lb' and 'ub' to numeric, coercing errors to NaN
    df['lb'] = pd.to_numeric(df['lb'])
    df['ub'] = pd.to_numeric(df['ub'])
    return df


@app.cell
def _(csv_files, held):
    df = pd.concat([read_csv(file) for file in csv_files] + [held], ignore_index=True)
    # on entries where lb != ub, time is None
    df.loc[df['lb'] != df['ub'], 'time'] = None
    return (df,)


@app.cell
def _(df):
    df
    return


@app.cell
def _(df):
    def check_inconsistencies(dataframe):
        """
        Checks for inconsistencies in graph coloring results for each instance.

        An inconsistency is found if:
        1. The maximum reported lower bound for an instance is greater than the
           minimum reported upper bound.
        2. Multiple different optimal values (where lb == ub) are reported for the
           same instance.

        Args:
            dataframe (pd.DataFrame): DataFrame with 'instance', 'lb', and 'ub' columns.

        Returns:
            dict: A dictionary mapping inconsistent instance names to a list of
                  strings describing the issues.
        """
        inconsistencies = {}
        # Group by instance to check each one individually
        for instance_name, group in dataframe.groupby('instance'):
            # Drop rows where bounds are not available for comparison
            valid_bounds_group = group#.dropna(subset=['lb', 'ub'])

            # Skip if there's not enough data to compare
            if len(valid_bounds_group) < 2:
                continue

            instance_messages = []

            # Check 1: Is any lower bound greater than any upper bound?
            max_lb = valid_bounds_group['lb'].max()
            min_ub = valid_bounds_group['ub'].min()

            if max_lb > min_ub:
                msg = (
                    f"Contradiction: Max lower bound ({max_lb}) is greater than "
                    f"min upper bound ({min_ub})."
                )
                instance_messages.append(msg)

            # Check 2: Are there multiple different optimal values reported?
            optimal_rows = valid_bounds_group[valid_bounds_group['lb'] == valid_bounds_group['ub']]
            if not optimal_rows.empty:
                optimal_values = optimal_rows['ub'].unique()
                if len(optimal_values) > 1:
                    msg = f"Multiple different optimal values reported: {sorted(list(optimal_values))}."
                    instance_messages.append(msg)

            if instance_messages:
                inconsistencies[instance_name] = instance_messages

        return inconsistencies

    # Find and display the inconsistencies from the df DataFrame
    inconsistent_results = check_inconsistencies(df)

    # Display the results in a markdown format
    if not inconsistent_results:
        results_md = mo.md("✅ No inconsistencies found in the dataset.")
    else:
        md_string = "### 🚨 Inconsistent Results Found\n\n"
        for instance, messages in inconsistent_results.items():
            md_string += f"**Instance: `{instance}`**\n"
            for msg in messages:
                md_string += f"- {msg}\n"
            # Add the relevant data for context
            md_string += "```\n"
            md_string += df[df['instance'] == instance][['source', 'lb', 'ub', 'time']].to_string(index=False)
            md_string += "\n```\n---\n"
        results_md = mo.md(md_string)

    results_md
    return


@app.cell
def _(df):
    # 1. Identify solved instances and find the one with the best time for each.
    # A solved instance is one where lb == ub.
    solved_df = df.dropna(subset=['lb', 'ub', 'time'])[df['lb'] == df['ub']].copy()
    # By sorting by time and dropping duplicates, we keep the fastest solved time.
    best_solved_df = solved_df.sort_values('time').drop_duplicates('instance', keep='first')

    # 2. Identify instances that have not been solved to optimality in any entry.
    solved_instances = best_solved_df['instance'].unique()
    unsolved_df = df[~df['instance'].isin(solved_instances)].copy()

    # 3. For each unsolved instance, find the best lower bound and best upper bound.
    unsolved_summary = []
    for instance2, group in unsolved_df.groupby('instance'):
        # Get the index of the max lower bound
        best_lb_idx = group['lb'].idxmax()
        # Get the index of the min upper bound
        best_ub_idx = group['ub'].idxmin()

        # Check if idxmax() returned NaN (meaning all 'lb' values were NaN)
        if pd.isna(best_lb_idx):
            # If all lbs are NaN, just grab the first row as a reference
            # Its 'lb' value will be NaN, which is correct
            best_lb_row = group.iloc[0]
        else:
            best_lb_row = group.loc[best_lb_idx]

        # Check if idxmin() returned NaN (meaning all 'ub' values were NaN)
        if pd.isna(best_ub_idx):
            # If all ubs are NaN, just grab the first row as a reference
            best_ub_row = group.iloc[0]
        else:
            best_ub_row = group.loc[best_ub_idx]

        # Combine the sources for the best LB and UB, ensuring uniqueness
        sources = sorted(list({best_lb_row['source'], best_ub_row['source']}))

        unsolved_summary.append({
            'instance': instance2,
            'lb': best_lb_row['lb'],  # This will be NaN if all were NaN
            'ub': best_ub_row['ub'],  # This will be NaN if all were NaN
            'time': None,
            'source': ', '.join(sources)
        })

    best_unsolved_df = pd.DataFrame(unsolved_summary)

    # 4. Concatenate the results for solved and unsolved instances.
    best_results_df = pd.concat([best_solved_df, best_unsolved_df], ignore_index=True)

    # Sort the final DataFrame by instance name for consistency.
    best_results_df = best_results_df.sort_values('instance').reset_index(drop=True)

    best_results_df
    return (best_results_df,)


@app.cell
def _(best_results_df):
    # write best_results_df to best_exact.csv
    best_results_df.to_csv("best_exact.csv", index=False)
    return


@app.cell
def _():
    # read "../metadata.csv"
    metadata = pd.read_csv("../metadata.csv")
    metadata
    return (metadata,)


@app.cell
def _():
    hoeve_best_known = pd.read_csv("hoeve21.csv")
    hoeve_best_known
    return (hoeve_best_known,)


@app.cell
def _(best_results_df, hoeve_best_known, metadata):
    # Table @data://metadata has some metadata about some graph coloring instances. @data://hoeve_best_known is a table from a recent paper citing some "best known results". Update in @data://metadata the lower bound and the upper bound if the @data://hoeve_best_known lb or ub is better. Also print a message saying you did so.

    updated_metadata = metadata.copy()
    for _, row in hoeve_best_known.iterrows():
        instance_name = row['instance']
        hoeve_lb = row['lb']
        hoeve_ub = row['ub']

        # Find the corresponding row in metadata
        meta_row = updated_metadata[updated_metadata['instance'] == instance_name]

        if not meta_row.empty:
            meta_index = meta_row.index[0]
            meta_lb = meta_row.at[meta_index, 'lb']
            meta_ub = meta_row.at[meta_index, 'ub']

            # Update lower bound if hoeve's is better
            if pd.notna(hoeve_lb) and (pd.isna(meta_lb) or hoeve_lb > meta_lb):
                updated_metadata.at[meta_index, 'lb'] = hoeve_lb
                print(f"Updated LB for instance '{instance_name}' from {meta_lb} to {hoeve_lb}.")

            # Update upper bound if hoeve's is better
            if pd.notna(hoeve_ub) and (pd.isna(meta_ub) or hoeve_ub < meta_ub):
                updated_metadata.at[meta_index, 'ub'] = hoeve_ub
                print(f"Updated UB for instance '{instance_name}' from {meta_ub} to {hoeve_ub}.")

    for _, row in best_results_df.iterrows():
        instance_name = row['instance']
        hoeve_lb2 = row['lb']
        hoeve_ub2 = row['ub']

        # Find the corresponding row in metadata
        meta_row = updated_metadata[updated_metadata['instance'] == instance_name]

        if not meta_row.empty:
            meta_index = meta_row.index[0]
            meta_lb = meta_row.at[meta_index, 'lb']
            meta_ub = meta_row.at[meta_index, 'ub']

            # Update lower bound if hoeve's is better
            if pd.notna(hoeve_lb2) and (pd.isna(meta_lb) or hoeve_lb2 > meta_lb):
                updated_metadata.at[meta_index, 'lb'] = hoeve_lb2
                print(f"Updated LB for instance '{instance_name}' from {meta_lb} to {hoeve_lb2}.")

            # Update upper bound if hoeve's is better
            if pd.notna(hoeve_ub2) and (pd.isna(meta_ub) or hoeve_ub2 < meta_ub):
                updated_metadata.at[meta_index, 'ub'] = hoeve_ub2
                print(f"Updated UB for instance '{instance_name}' from {meta_ub} to {hoeve_ub2}.")

    # Save the updated metadata
    # updated_metadata.to_csv("../metadata.csv", index=False)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
