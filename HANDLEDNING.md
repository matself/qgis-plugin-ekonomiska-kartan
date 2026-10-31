# Handledning: Ekonomiska kartan i QGIS

Med det här tillägget hämtar du inskannade blad ur Lantmäteriets *Ekonomiska kartan* (1950- till
1980-talen) och lägger dem direkt som lager i QGIS. Bladen är öppen data, du behöver inget konto.

## Installera

1. Hämta `ekonomiska_kartan-0.1.0-experimental.zip` under *Releases* på GitHub.
2. I QGIS: **Tillägg > Hantera och installera tillägg > Installera från ZIP**, välj filen.
3. Klicka på tilläggets ikon i verktygsfältet. Panelen öppnas till höger.

## Hämta blad, steg för steg

**1. Visa var du vill ha kartor**
När du öppnar tillägget läggs lagret *Ekonomiska kartan - grid* till. Det visar bladindelningen
(rutor på 5 x 5 km med bladnamn). Zoomar du ut visas större rutor. Vill du slippa det döljer du
lagret i lagerlistan med ögat, precis som ett vanligt lager.

> **Viktigt: rutnätet är konstruerat, inte Lantmäteriets egen indelning.** Tillägget räknar
> fram rutorna ur bladnamnens system i stället för att ha med Lantmäteriets stora kartfil över
> bladgränserna. Då blir tillägget litet och enkelt att installera. Rutnätet stämmer för nästan alla
> blad, men visar inte den verkliga utbredningen: vissa blad är skannade större än sin ruta,
> kantblad kan vara oregelbundna och en del rutor har inget blad alls. Det som visar hur ett blad
> verkligen ligger är själva kartbilden när den är inläst.

**2. Peka ut ett område**
Välj ett av tre sätt:
- **Rita sökruta på kartan**: dra en rektangel, eller klicka en gång för att välja ett enda blad.
- **Använd aktuellt kartutsnitt**: söker i det du ser på skärmen.
- Vill du börja om: **Rensa sökrutan**.

Sökningen får högst omfatta 100 blad. Gör rutan mindre om det blir för många.

**3. Välj vilka blad du vill ha**
Bladen som finns visas i listan, alla förbockade från början. På kartan syns de som rutor:
grå = finns, grön = förbockad, orange ram = raden du har klickat på i listan.
- Bocka ur de du inte vill ha, eller använd **Välj alla** / **Välj inga**.
- Eller klicka på **Välj blad i kartan** och klicka direkt på ett blad för att välja eller välja
  bort det. Dra en rektangel för att välja flera (Skift lägger till, Ctrl tar bort).
- Finns flera år (**Utgåva**) för ett blad är det senaste valt. Byt i rullistan om du vill ha ett
  annat.

Under listan står hur många blad du valt och ungefär hur många MB det blir. Ett blad är ofta
50–70 MB.

**4. Välj var filerna ska ligga**
Klicka på **…** vid **Nedladdningsmapp** och välj en mapp. Filer som redan finns där hämtas inte
en gång till.

**5. Välj var lagren hamnar i lagerlistan**
Under **Lägg i lagerlistan** kan du välja *Överst*, *Ovanför valt lager* eller *Underst*. Det
sista passar bra om du vill ha kartorna under dina egna lager.

**6. Hämta**
Klicka på **Hämta och ladda in**. Hämtningen sker i bakgrunden, så du kan fortsätta arbeta i QGIS.
Bladen hamnar i en grupp som heter *Ekonomiska kartan*. Väljer du 50 blad eller fler får du en
fråga först, eftersom det blir mycket data.

## Om du ser det här

- **⚠ vid storleken:** kartan är skannad större än sin ruta. Tillägget placerar den rätt när den
  läses in, och den extra kartytan utanför rutan finns kvar.
- **(overifierad) efter lagernamnet:** placeringen är osäker. Jämför med en bakgrundskarta.
- **(tom) efter lagernamnet:** filen innehåller ingen bild, felet finns i Lantmäteriets data. Bladet
  blir helt svart.
- **(ingen tif):** det finns ingen bildfil för det bladet, så det kan inte hämtas.
- **Blad utan karta:** rutor i området som Lantmäteriet inte har något blad för.

## Bra att veta

- Sökrutnätet är framräknat av tillägget och är inte kartverkets verkliga bladindelning (se
  rutan under steg 1). En ruta i rutnätet betyder alltså inte säkert att det finns ett blad, och
  ett blad kan sträcka sig utanför sin ruta.
- Det är gamla skannade kartor. Några blad saknas, ligger lite fel eller har skador. Tillägget
  försöker inte rätta alla fel, så kontrollera mot en bakgrundskarta när det är viktigt.
- Ekonomiska kartan i Norrland (*Norrlands_inland*) saknas, eftersom de skanningarna inte har
  någon placering på kartan.
- Mer teknisk information finns i [README.md](README.md). Fel och önskemål kan du lämna under
  *Issues* på GitHub.
