"""BTS T-100 Segment Summary by Origin Airport (Socrata, data.bts.gov, dataset r495-tyji).

Monthly departures, passengers, seats, load factor, distance, domestic vs international.
Aggregation is done server-side with SoQL (e.g. sums grouped by year) so we never pull millions of rows.
No API key required.
"""
