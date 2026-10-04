# Store geocoding tiers

Generated from data/stores.json. Classification mirrors the seeder exactly.

- **Tier 1 — precise location** (own geocoded coordinate): **103**
- **Tier 2 — locality, not precise street** (backfilled to area centroid): **2**
- **Tier 3 — fallback** (no own coord, no area neighbour → previously city centre; now HIDDEN, coords blank for you to fill): **26**

---

## Tier 3 — fallback (HIDDEN from users; fill in lat/lng, then unhide automatically)

| id | name | locality_raw | canonical_area | lat | lng |
|---|---|---|---|---|---|
| blr-0014 | Sri Krishnarajendra Market | Kr Market/chikpet | KR Market | | |
| blr-0017 | Remode racks | Mathikere Extension | Mathikere | | |
| blr-0033 | Thrift Therapy | Ramaswamipalaya Jayamahal | Jayamahal | | |
| blr-0046 | Flora Fountain | Opp Old Zara Churchgate | Opp Old Zara Churchgate | | |
| blr-0053 | Old Cloth merchant association | Muhammed Hayat Street,Near KR Market Bengaluru | KR Market | | |
| blr-0059 | (Street) | Malleshwaram 8th cross street shopping | Malleshwaram 8th cross street shopping | | |
| blr-0062 | Chikpet Hyat Street | Bengaluru,near complex kr market | KR Market | | |
| blr-0070 | Rohini Fashion | 3rd Cross Rd,Venkatewara layout | Venkatewara layout | | |
| blr-0071 | Amex Sports | SG Palya main road,Opposite to Lakshmi theatre | Opposite to Lakshmi theatre | | |
| blr-0073 | Dreams Boutique | Taverekere,SG Palya,Opposite Christ Backgate | Opposite Christ Backgate | | |
| blr-0083 | Akshay Trends | Taverekere Main road,Opposite to health india hospital | Opposite to health india hospital | | |
| blr-0084 | Meena Fashion | Muni Reddy Building,Taverekere main road,Near health india hospital | Near health india hospital | | |
| blr-0085 | Sangam Textiles | 1st floor,Taverkkere main road,opposite to Mangaluru lunch home | opposite to Mangaluru lunch home | | |
| blr-0086 | Mannlich | 11,6th cross road,Taverekere main road,Btm Ist stage | Btm Ist stage | | |
| blr-0087 | Cotton wear house | 12,2and cross road,Maruthi nagar 1st stage,Taverekere main rd | Taverekere main | | |
| blr-0090 | Retro Store | 1st cross road,Taverekere,Cashier layout | Cashier layout | | |
| blr-0091 | Vintage | 1st cross road,Taverekere,Cashier layout | Cashier layout | | |
| blr-0100 | Boom | 14 th cross roadOld Madiwala | 14 th cross roadOld Madiwala | | |
| blr-0109 | Shoppers points | 25/1 Maruthi nagar main rd,Madiwala new extension | Madiwala new extension | | |
| blr-0110 | Chandrika Textiles | 15,Maruthi Nagar main rd,Madiwala new extension | Madiwala new extension | | |
| blr-0111 | Troadiez | Shop no 5,8-th cross road,Madiwala new extension | Madiwala new extension | | |
| blr-0112 | Janani collections | 8-th cross road,Madiwala new extensio | Madiwala new extensio | | |
| blr-0114 | Krishna Boutique | 9/19,1st main road,Madiwala new extension | Madiwala new extension | | |
| blr-0120 | Pink City | 9-20,Madiwala new extension | Madiwala new extension | | |
| blr-0121 | Mahalaxmi textiles showroom | 19/61,3rd Cross rd,Btm Ist stage | Btm Ist stage | | |
| blr-0124 | Rajalaksmi textiles | 12/64 Maruthi nagar main rd,Madiwala new extension | Madiwala new extension | | |

## Tier 2 — locality, not precise street (visible; coords are the area centroid)

| id | name | locality_raw | canonical_area | lat | lng |
|---|---|---|---|---|---|
| blr-0015 | Escape Closet | J.P Nagar 5th Phase | JP Nagar | None | None |
| blr-0021 | Goodwill streets | Narayan Pillai Street, Commercial Street Cross | Commercial Street | None | None |

## Tier 1 — precise location (visible; own geocoded coordinate)

| id | name | locality_raw | canonical_area | lat | lng |
|---|---|---|---|---|---|
| blr-0001 | EcoDhaga | Koramangala | Koramangala | 12.9357366 | 77.624081 |
| blr-0002 | Love Me Twice | Indiranagar | Indiranagar | 12.9732913 | 77.6404672 |
| blr-0003 | Thrft | Kothanur | Kothanur | 12.8701259 | 77.5820178 |
| blr-0004 | The Preloved Co | Sivanchetti Gardens | Sivanchetti Gardens | 12.9845768 | 77.6131984 |
| blr-0005 | Escape Closet | JP Nagar | JP Nagar | 12.9096941 | 77.5866067 |
| blr-0006 | Raheja Arcade | Koramangala | Koramangala | 12.9357366 | 77.624081 |
| blr-0007 | Sri Venkateshwara Garments | BTM 1st Stage,Gangothri Circle | Gangothri Circle | 12.9196341 | 77.6129048 |
| blr-0008 | Thrift Store | Chandra Layout | Chandra Layout | 12.955333 | 77.5238903 |
| blr-0009 | Ramachandrapura Market | Rajajinagar | Rajajinagar | 13.0005232 | 77.5496166 |
| blr-0010 | Junk in the Trunk Thrift Store | Lingarajapuram | Lingarajapuram | 13.0093949 | 77.6267881 |
| blr-0011 | Vintage Street | Church Street | Church Street | 12.9734314 | 77.6517971 |
| blr-0012 | Viintage Clothing | BTM Layout | BTM Layout | 12.9140008 | 77.6102821 |
| blr-0013 | Evening Bazar | Shivaji Nagar | Shivaji Nagar | 12.9883249 | 77.6004488 |
| blr-0016 | MR Arcade | Koramangala | Koramangala | 12.9357366 | 77.624081 |
| blr-0018 | Ts Traders | Shampura main road | Shampura | 13.0288569 | 77.6157713 |
| blr-0019 | Jaaf Blr | Kothanur | Kothanur | 12.8701259 | 77.5820178 |
| blr-0020 | Re Store | Pattandur Agrahara Maithri Layout 4th Cross Rd,Whitefield | Whitefield | 12.9957428 | 77.7579489 |
| blr-0022 | Pretty Little Fits | HillCrest,House of Hiranandani | House of Hiranandani | 12.9723543 | 77.6409111 |
| blr-0023 | Sri Venkateshwara Garments | 211, Rhs Plaza, 253, 14th Main Rd, Sector 7, Hsr Layout, Bengaluru | HSR Layout | 12.9767936 | 77.590082 |
| blr-0024 | Shaan Creations | Gullama Road,Kacharakanahalli | Kacharakanahalli | 13.0222071 | 77.6319093 |
| blr-0025 | Thrift By Ara | Krishna Gardens,Kattigenahalli | Kattigenahalli | 13.1177735 | 77.6261222 |
| blr-0026 | Vintage Clothing | Taverekere,Bengaluru | Taverekere | 12.9767936 | 77.590082 |
| blr-0027 | Bangaluru Brand Wrehouse | 3rd Phase,JP Nagar | JP Nagar | 12.9100191 | 77.5925018 |
| blr-0028 | Sanzy Old Cloth Merchant | Am Street,Kalasipalaya | Kalasipalaya | 12.9605656 | 77.5767802 |
| blr-0029 | Old Clothes Buyyers Banglore | Hayanth Street,Kalasipalaya | Kalasipalaya | 12.958189 | 77.5768148 |
| blr-0030 | Thrift 7/11 | Koramangala 8th Block | Koramangala | 12.9408685 | 77.617338 |
| blr-0031 | Eloutfit Thrift Store | Bannerghata Road,Arekere | Arekere | 12.8872086 | 77.5960493 |
| blr-0032 | Thrift Fiction | 27th Main road,HSR Layout | HSR Layout | 12.9100899 | 77.6518771 |
| blr-0034 | Thrift Bazar | Electronic City | Electronic City | 12.8487599 | 77.648253 |
| blr-0035 | Thrift Hands | SG Palya,Bengaluru | SG Palya | 12.9318731 | 77.6076887 |
| blr-0036 | Thrift India | Electronic City,Bengaluru | Electronic City | 12.8487599 | 77.648253 |
| blr-0037 | Collections Reloved | Richards Town,Bengaluru | Richards Town | 13.0042369 | 77.6170601 |
| blr-0038 | Frisson | RBI Layout,JP Nagar | JP Nagar | 12.9096941 | 77.5866067 |
| blr-0039 | MD fashion | 1st Cross,Kallappa Block,Sriramapura | Sriramapura | 12.8715399 | 77.6842714 |
| blr-0040 | AYM Enterprises | Bapuji,Nagar | Bapuji Nagar | 12.955015 | 77.540974 |
| blr-0041 | Brands and Brother | Bendre Nagar | Bendre Nagar | 12.910206 | 77.5639218 |
| blr-0042 | Prabhat Barcade | Koramangala 8th Block | Koramangala | 12.9408685 | 77.617338 |
| blr-0043 | Wolf Street | BTM Layout | BTM Layout | 12.9140008 | 77.6102821 |
| blr-0044 | BrothersHappy | Koramangala | Koramangala | 12.9357366 | 77.624081 |
| blr-0045 | Drift House | JP Nagar | JP Nagar | 12.9096941 | 77.5866067 |
| blr-0047 | Bhavika Exports | Commercial Street | Commercial Street | 12.9822157 | 77.6082513 |
| blr-0048 | The T Shirt Treasure | BTM Layout | BTM Layout | 12.9140008 | 77.6102821 |
| blr-0049 | Jayanagar Shopping Complex | Jayanagar 4th Block | Jayanagar | 12.9265737 | 77.5835041 |
| blr-0050 | Tibetan Market | Rest House Road | Rest House | 12.9737631 | 77.6064116 |
| blr-0051 | Thrift Store | Attiguppe | Attiguppe | 12.9618581 | 77.5335932 |
| blr-0052 | Higns Picks | Hbr Layout | Hbr Layout | 13.031992 | 77.6280789 |
| blr-0054 | Taalish | Beside Sindhoor Café,Madiwala | Madiwala | 12.9218931 | 77.6177348 |
| blr-0055 | Bhavika Exports | Ibrahim Saheeb Street,Shivajinagar | Shivaji Nagar | 12.9855286 | 77.6054496 |
| blr-0056 | Globus Vault | Bengaluru,HSR | HSR | 12.9086277 | 77.6279831 |
| blr-0057 | Fashion Plus | Near Merry Berry fashions,Jayanagar 4th Block | Jayanagar | 12.9265737 | 77.5835041 |
| blr-0058 | (Street) | Jayanagar 4th Block | Jayanagar | 12.9265737 | 77.5835041 |
| blr-0060 | Y Not! | Kamaraj Rd,Tasker Town,Shivaji Nagar,Bengaluru | Shivaji Nagar | 12.9767936 | 77.590082 |
| blr-0061 | UNORGANISED STORES | nan | nan | 12.935001 | 77.5931866 |
| blr-0063 | Dreams Fab World | Bhavani Nagar,Sg Palya | Sg Palya | 12.9328434 | 77.6094915 |
| blr-0064 | Fashion House | SG Palya,Bharathi Layout | Bharathi Layout | 12.9328434 | 77.6094915 |
| blr-0065 | Stash In | SG Palya main road,Bharathi Layout | Bharathi Layout | 12.9328434 | 77.6094915 |
| blr-0066 | Skinn | SG Palya main road,Bhavani nagar | Bhavani nagar | 13.0020764 | 77.619925 |
| blr-0067 | Laxmi Textiles | Near Srinivasa theatre,Venkateswara layout,SG Palya | SG Palya | 12.9328434 | 77.6094915 |
| blr-0068 | Look Smart | SG Palya main road,Venkateswara layout | Venkateswara layout | 12.9093844 | 77.6378877 |
| blr-0069 | 90s Vogue | Near Srinivasa theatre,Venkateswara layout,SG Palya | SG Palya | 12.9328434 | 77.6094915 |
| blr-0072 | Oxxy | Drc Post,Venkateswara layout,Koramangala | Koramangala | 12.9357366 | 77.624081 |
| blr-0074 | M I Enterprises Rug Shop | Jayanagar,Bengaluru | Jayanagar | 12.9292731 | 77.5824229 |
| blr-0075 | Nakshathra Collections,Malleshwaram | Malleshwaram | Malleshwaram | 13.0027353 | 77.5703253 |
| blr-0076 | Bomber | Drc Post,Venkateswara layout,SG Palya | SG Palya | 12.9328434 | 77.6094915 |
| blr-0077 | Hope | 1st Main road,Taverkere,S G Palya | S G Palya | 12.9324773 | 77.6046399 |
| blr-0078 | Aashis's | Taverekere Main Rd,Krishna Murthi layout, S G Palya | S G Palya | 12.9324773 | 77.6046399 |
| blr-0079 | Base | Taverekere Main Rd,Krishna Murthi layout, S G Palya | S G Palya | 12.9324773 | 77.6046399 |
| blr-0080 | Queens Collection | Taverekere Main Rd,2and Stage, S G Palya | S G Palya | 12.9324773 | 77.6046399 |
| blr-0081 | Plants factory outlet | Taverekere Main Rd,Krishna Murthi layout, S G Palya | S G Palya | 12.9324773 | 77.6046399 |
| blr-0082 | Ernesto | Taverekere main rd,near Balaji Theatre,S G Palya | S G Palya | 12.9324773 | 77.6046399 |
| blr-0088 | KM Silks Hrishiti's | Suree's Blr residence,Btm 1st stage,Taverekere,Madiwala | Madiwala | 12.9218931 | 77.6177348 |
| blr-0089 | Abeeha Collection | Taverekere,Cashier Layout,1st Stage | 1st Stage | 12.9393328 | 77.5539819 |
| blr-0092 | Oxxo | 1st cross road,Taverekere,Maruti Nagar | Maruti Nagar | 13.00317 | 77.6326118 |
| blr-0093 | (Street Shop) | 16,2and A Main road,Old Madiwala | Old Madiwala | 12.9612429 | 77.6369997 |
| blr-0094 | F.O.P | 1188,1st Cross road,Taverekere main road,Btm 1st Stage | Btm 1st Stage | 12.916193 | 77.6053993 |
| blr-0095 | Jackfader | 1188,1st Cross road,Taverekere main road,Btm 1st Stage | Btm 1st Stage | 12.916193 | 77.6053993 |
| blr-0096 | Cotton sangam sale | 17 cross,6th main road,Old Madiwala,1st stage | 1st stage | 12.9393328 | 77.5539819 |
| blr-0097 | PRO | Old Madiwala,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0098 | Sevens | 1st Main road,Old Madiwala | Old Madiwala | 12.9612429 | 77.6369997 |
| blr-0099 | Colors | 1st Main road,Old Madiwala | Old Madiwala | 12.9612429 | 77.6369997 |
| blr-0101 | Adiba Collections | 1st Main road,Old Madiwala | Old Madiwala | 12.9612429 | 77.6369997 |
| blr-0102 | Velvet Handles | 1st Main road,Old Madiwala | Old Madiwala | 12.9612429 | 77.6369997 |
| blr-0103 | Femzy Studio | Sri Ragavendra Complex,Maruthi nagar main rd | Maruthi nagar main | 13.0094565 | 77.6431811 |
| blr-0104 | Passion Ladies hub | 9-9,Old madiwala,1st Stage,Btm 1st Stage | Btm 1st Stage | 12.916193 | 77.6053993 |
| blr-0105 | House of Fashion | 25,old Madiwala,1st stage,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0106 | Go Fidaa | 30,Maruthi nagar main rd,Old Madiwala | Old Madiwala | 12.9612429 | 77.6369997 |
| blr-0107 | (Street Shop) | 202,5th cross road,Madiwala,1st Stage,Koramangala | Koramangala | 12.9357366 | 77.624081 |
| blr-0108 | Maruthi textiles | 202,5th cross road,Madiwala,1st Stage,Koramangala | Koramangala | 12.9357366 | 77.624081 |
| blr-0113 | Rajshree collection | 10/15,1st main road,Madiwala 1st stage | Madiwala 1st stage | 12.9610268 | 77.6386351 |
| blr-0115 | Swastik Fshion | 8/19,Madiwala new extension,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0116 | Laxmi Textiles | 24,1st main road,Madiwala new extension,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0117 | Shifa collection | 9/17,Maruthi nagar main rd,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0118 | Oxxy | 9/17 marthi nagar main rd,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0119 | Esperanto | 15,3rd cross road,Btm 1st stage | Btm 1st stage | 12.9178327 | 77.6134779 |
| blr-0122 | Ayesha collections | Madiwala new extension,Maruthi nagar,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0123 | Adoxe | Madiwala new extension,Maruthi nagar,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0125 | StyleX | 01,Old Madiwala,1st Stage,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0126 | Urbano | 01,Old Madiwala,1st Stage,Btm 1st stage | Btm 1st stage | 12.916193 | 77.6053993 |
| blr-0127 | (Street Shop) | 25,Maruthi Nagar,Btm layout | BTM Layout | 12.9234788 | 77.6146246 |
| blr-0128 | Zella | 25,Maruthi Nagar,Btm layout | BTM Layout | 12.9234788 | 77.6146246 |
| blr-0129 | Style base | 11/7,1st cross road,S G Palya | S G Palya | 12.9338122 | 77.6083601 |
| blr-0130 | MR Brandmen | 25/3,1st cross road,Main road madiwala | Main road madiwala | 12.9175652 | 77.6203154 |
| blr-0131 | (Street shop) | Madiwala,S G Palya | S G Palya | 12.9324773 | 77.6046399 |
