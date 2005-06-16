<?xml version='1.0'?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:fo="http://www.w3.org/1999/XSL/Format"
  xmlns:xi='http://www.w3.org/2001/XInclude'
  xmlns:exsl="http://exslt.org/common"
  version='1.0'>
  <xsl:param name="html.stylesheet" select="'css/style.css'" />
    <xsl:param name="generate.index" select="1"/>

  <xsl:param name="default.table.width" select="'780'"/>
  <xsl:param name="chapter.autolabel" select="1"/>
  <xsl:param name="section.autolabel" select="1"/>
  <xsl:param name="table.cell.border.color" select="''"/>
  <xsl:param name="table.borders.with.css" select="1"/>
  <xsl:param name="html.cellspacing" select="'0'"/>
  <xsl:param name="qanda.defaultlabel">number</xsl:param>
  <xsl:param name="qanda.inherit.numeration" select="0"/>
  <xsl:param name="css.decoration">0</xsl:param>  
  <xsl:param name="chunk.section.depth" select="1"/>
  
  <xsl:param name="local.l10n.xml" select="document('')"/>
  <l:i18n xmlns:l="http://docbook.sourceforge.net/xmlns/l10n/1.0">
    <l:l10n xmlns:l="http://docbook.sourceforge.net/xmlns/l10n/1.0" language="en">
     <l:context name="xref">
        <l:template name="chapter" style="title" text="Chapter %n, %t"/>
        <l:template name="chapter" text="Chapter %n"/>
      </l:context>
    </l:l10n>
  </l:i18n>
</xsl:stylesheet>
